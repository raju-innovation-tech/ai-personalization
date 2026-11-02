"""Pure unit tests of the recommendation engine (no database)."""
from app.recommendations.engine import ProductInfo, Snapshot


def P(pid, name, category, brand="Acme", price=1000.0, **kw):
    return ProductInfo(product_id=pid, name=name, category=category, brand=brand, price=price, **kw)


CATALOG = [
    P("L1", "Acme Pro Laptop", "Laptops", "Acme", 60000),
    P("L2", "Acme Air Laptop", "Laptops", "Acme", 55000),
    P("L3", "Zeta Book Laptop", "Laptops", "Zeta", 80000),
    P("B1", "Acme Sleeve Laptop Bag", "Laptop Bags", "Acme", 1500),
    P("B2", "Zeta Case Laptop Bag", "Laptop Bags", "Zeta", 1800),
    P("S1", "Run Fast Shoes", "Running Shoes", "Nike", 5000),
    P("S2", "Run Far Shoes", "Running Shoes", "Nike", 5200),
    P("X1", "Hidden Gem Wallet", "Wallets", "Fossil", 900, in_stock=False),
    P("X2", "Retired Wallet", "Wallets", "Fossil", 950, is_active=False),
]


def build(interactions=(), baskets=(), **kw):
    return Snapshot.build(CATALOG, list(interactions), list(baskets), **kw)


def test_popularity_orders_by_weighted_interactions():
    snap = build([
        ("u1", "L1", "PURCHASE", 1.0), ("u2", "L1", "PRODUCT_VIEW", 1.0),
        ("u3", "S1", "PRODUCT_VIEW", 1.0),
    ])
    ranked = [s.product_id for s in snap.popular(5)]
    assert ranked[:2] == ["L1", "S1"]
    assert snap.popular(1)[0].score == 1.0


def test_inactive_and_out_of_stock_never_recommended():
    snap = build([("u1", "X1", "PURCHASE", 5.0), ("u1", "X2", "PURCHASE", 5.0)])
    ids = {s.product_id for s in snap.popular(20)}
    assert "X1" not in ids and "X2" not in ids
    assert "X1" in {s.product_id for s in build([("u1", "X1", "PURCHASE", 5.0)], exclude_out_of_stock=False).popular(20)}


def test_negative_events_reduce_interest():
    snap = build([("u1", "L1", "PRODUCT_VIEW", 1.0), ("u1", "L1", "PURCHASE_CANCELLED", 1.0)])
    assert not snap.has_history("u1")  # 1 - 8 <= 0 -> clamped away


def test_time_decay_input_is_respected():
    snap = build([("u1", "L1", "PURCHASE", 0.1), ("u2", "S1", "PRODUCT_VIEW", 1.0)])
    assert snap.popular(1)[0].product_id == "S1"  # old purchase (decayed) < fresh view


def test_similar_prefers_same_category_and_brand():
    snap = build()
    result = snap.similar("L1", 3)
    assert [s.product_id for s in result][:2] == ["L2", "L3"]
    assert all(s.product_id != "L1" for s in result)


def test_similar_fills_with_popular_when_few_neighbours():
    snap = build([("u1", "S1", "PRODUCT_VIEW", 1.0)])
    assert len(snap.similar("S1", 6)) == 6


def test_collaborative_neighbours_use_cooccurring_users():
    interactions = []
    for u in ("a", "b", "c", "d"):
        interactions += [(u, "L1", "PURCHASE", 1.0), (u, "S1", "PURCHASE", 1.0)]
    snap = build(interactions)
    assert snap.cf_neighbors("L1")[0][0] == "S1"


def test_frequently_bought_requires_min_support():
    baskets = [("a", "s1", "L1"), ("a", "s1", "B1"), ("b", "s2", "L1"), ("b", "s2", "B1"), ("c", "s3", "L1"), ("c", "s3", "B2")]
    snap = build(baskets=baskets, fbt_min_support=2)
    result = snap.frequently_bought_together("L1", 5)
    assert result[0].product_id == "B1" and result[0].algorithm == "fbt"
    assert "B2" not in {s.product_id for s in result if s.algorithm == "fbt"}  # support 1


def test_frequently_bought_is_symmetric():
    baskets = [("a", "s1", "L1"), ("a", "s1", "B1"), ("b", "s2", "L1"), ("b", "s2", "B1")]
    snap = build(baskets=baskets)
    assert snap.frequently_bought_together("B1", 1)[0].product_id == "L1"


def test_for_user_cold_start_is_popular():
    snap = build([("u1", "L1", "PRODUCT_VIEW", 1.0)])
    items, algorithm = snap.for_user("nobody", 3)
    assert algorithm == "popular" and items


def test_for_user_hybrid_excludes_purchased_and_stays_relevant():
    interactions = [("me", "L1", "PURCHASE", 1.0), ("me", "L2", "PRODUCT_VIEW", 1.0)]
    for u in ("a", "b", "c"):  # other shoppers who liked laptops also viewed laptop L3
        interactions += [(u, "L1", "PRODUCT_VIEW", 1.0), (u, "L3", "PURCHASE", 1.0)]
    snap = build(interactions)
    items, algorithm = snap.for_user("me", 5)
    ids = [s.product_id for s in items]
    assert algorithm == "hybrid"
    assert "L1" not in ids                       # already purchased
    assert ids[0] in {"L3", "L2"}                # relevant item first
    assert len(ids) == len(set(ids))


def test_limit_is_respected_and_no_duplicates():
    snap = build([("me", "S1", "PURCHASE", 1.0)])
    items, _ = snap.for_user("me", 4)
    assert len(items) == 4 and len({s.product_id for s in items}) == 4
