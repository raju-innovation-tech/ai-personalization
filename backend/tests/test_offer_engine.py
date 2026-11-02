"""Pure unit tests of the offer engine (no database)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.offers.engine import (
    REASON_MESSAGES,
    Context,
    OfferRule,
    Usage,
    check_eligibility,
    compute_discount,
    effective_status,
    rank_offers,
)

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


def offer(**kw) -> OfferRule:
    base = dict(id="1", code="TEST", name="Test", offer_type="percent_off", value=10.0, status="active")
    base.update(kw)
    return OfferRule(**base)


# ------------------------------------------------------------ effective status
@pytest.mark.parametrize(
    "kw, expected",
    [
        (dict(status="draft"), "draft"),
        (dict(status="paused"), "paused"),
        (dict(status="ended"), "ended"),
        (dict(), "active"),
        (dict(starts_at=NOW + timedelta(days=1)), "scheduled"),
        (dict(ends_at=NOW - timedelta(seconds=1)), "expired"),
        (dict(ends_at=NOW), "expired"),                                   # the end instant itself is already over
        (dict(starts_at=NOW - timedelta(days=1), ends_at=NOW + timedelta(days=1)), "active"),
        (dict(status="paused", ends_at=NOW - timedelta(days=1)), "paused"),  # stored status wins unless active
    ],
)
def test_effective_status(kw, expected):
    assert effective_status(offer(**kw), NOW) == expected


def test_naive_datetimes_are_treated_as_utc():
    naive_past = datetime(2026, 10, 1, 0, 0)
    assert effective_status(offer(ends_at=naive_past), NOW) == "expired"


# ------------------------------------------------------------------ eligibility
def check(o, usage=Usage(), ctx=Context()):
    return check_eligibility(o, usage, ctx, NOW)


def test_basic_eligibility_and_inactive_reasons():
    assert check(offer()) is None
    assert check(offer(status="draft")) == "NOT_ACTIVE"
    assert check(offer(status="paused")) == "NOT_ACTIVE"
    assert check(offer(status="ended")) == "NOT_ACTIVE"
    assert check(offer(starts_at=NOW + timedelta(hours=1))) == "NOT_STARTED"
    assert check(offer(ends_at=NOW - timedelta(hours=1))) == "EXPIRED"


def test_segment_targeting():
    o = offer(target_segments=("champions", "loyal"))
    assert check(o, ctx=Context(segment="champions")) is None
    assert check(o, ctx=Context(segment="lost")) == "NOT_ELIGIBLE"
    assert check(o, ctx=Context(segment=None)) == "NOT_ELIGIBLE"          # unscored customers get no targeted offers
    assert check(offer(), ctx=Context(segment=None)) is None              # open offers are for everyone


def test_budget_and_per_customer_limits():
    o = offer(max_redemptions=5, max_per_customer=2)
    assert check(o, Usage(total_redemptions=4, customer_redemptions=1)) is None
    assert check(o, Usage(total_redemptions=5)) == "LIMIT_REACHED"
    assert check(o, Usage(total_redemptions=1, customer_redemptions=2)) == "CUSTOMER_LIMIT_REACHED"
    assert check(offer(max_redemptions=None), Usage(total_redemptions=10**6)) is None


def test_minimum_order_value():
    o = offer(min_order_value=1000)
    assert check(o, ctx=Context(order_value=999.99)) == "MIN_ORDER_NOT_MET"
    assert check(o, ctx=Context(order_value=1000)) is None
    assert check(o, ctx=Context(order_value=None)) is None                # browsing: unknown cart


def test_category_targeting_browsing_vs_checkout():
    o = offer(target_categories=("Laptops",))
    assert check(o, ctx=Context(browsing_category="laptops")) is None     # case-insensitive
    assert check(o, ctx=Context(browsing_category="Shoes")) == "CATEGORY_NOT_MATCHED"
    assert check(o, ctx=Context()) is None                                # no browsing context -> allowed
    assert check(o, ctx=Context(checkout=True, categories=("Shoes", "LAPTOPS"))) is None
    assert check(o, ctx=Context(checkout=True, categories=("Shoes",))) == "CATEGORY_NOT_MATCHED"
    assert check(o, ctx=Context(checkout=True)) == "CATEGORY_NOT_MATCHED"  # checkout must prove the category


def test_every_reason_code_has_a_message():
    for code in ("NOT_ACTIVE", "NOT_STARTED", "EXPIRED", "NOT_ELIGIBLE", "LIMIT_REACHED",
                 "CUSTOMER_LIMIT_REACHED", "MIN_ORDER_NOT_MET", "CATEGORY_NOT_MATCHED", "OFFER_NOT_FOUND"):
        assert REASON_MESSAGES[code]


# --------------------------------------------------------------------- discount
@pytest.mark.parametrize(
    "kw, order, expected",
    [
        (dict(offer_type="percent_off", value=10), 2000, (200.0, False)),
        (dict(offer_type="percent_off", value=10, max_discount=150), 2000, (150.0, False)),   # cap
        (dict(offer_type="percent_off", value=33.33), 100, (33.33, False)),
        (dict(offer_type="fixed_off", value=500), 2000, (500.0, False)),
        (dict(offer_type="fixed_off", value=500), 300, (300.0, False)),                      # never more than the order
        (dict(offer_type="fixed_off", value=500, max_discount=100), 2000, (100.0, False)),
        (dict(offer_type="free_shipping", value=0), 2000, (0.0, True)),
        (dict(offer_type="percent_off", value=10), 0, (0.0, False)),
        (dict(offer_type="percent_off", value=10), None, (0.0, False)),
    ],
)
def test_compute_discount(kw, order, expected):
    assert compute_discount(offer(**kw), order) == expected


# ------------------------------------------------------------------------ ranking
def candidates(*offers, usage=Usage()):
    return [(o, usage) for o in offers]


def test_rank_filters_ineligible_and_prefers_targeted_offers():
    open_offer = offer(id="a", code="OPEN", value=20, priority=50)
    targeted = offer(id="b", code="VIP", value=10, priority=50, target_segments=("champions",))
    wrong_segment = offer(id="c", code="OTHER", target_segments=("lost",))
    draft = offer(id="d", code="DRAFT", status="draft")
    ctx = Context(segment="champions", segment_name="Champions")

    ranked = rank_offers(candidates(open_offer, targeted, wrong_segment, draft), ctx, NOW, limit=10)
    assert [r.offer.code for r in ranked] == ["VIP", "OPEN"]
    assert ranked[0].reason == "Made for Champions"
    assert ranked[0].score > ranked[1].score


def test_rank_category_interest_and_reasons():
    laptop = offer(id="a", code="LAP", target_categories=("Laptops",))
    ranked = rank_offers(candidates(laptop), Context(favorite_category="Laptops"), NOW, limit=5)
    assert ranked[0].reason == "Matches your interest in Laptops"


def test_rank_urgency_and_reason_text():
    soon = offer(id="a", code="SOON", ends_at=NOW + timedelta(days=2))
    later = offer(id="b", code="LATER", ends_at=NOW + timedelta(days=60))
    ranked = rank_offers(candidates(soon, later), Context(), NOW, limit=5)
    assert ranked[0].offer.code == "SOON" and ranked[0].reason == "Ends in 2 days"
    last_hours = offer(id="c", code="HOURS", ends_at=NOW + timedelta(hours=5))
    assert rank_offers(candidates(last_hours), Context(), NOW, 5)[0].reason == "Ends soon"


def test_rank_priority_value_and_stable_ties():
    low = offer(id="a", code="B-LOW", priority=10)
    high = offer(id="b", code="A-HIGH", priority=90)
    assert [r.offer.code for r in rank_offers(candidates(low, high), Context(), NOW, 5)] == ["A-HIGH", "B-LOW"]
    twin1, twin2 = offer(id="x", code="TWIN-B"), offer(id="y", code="TWIN-A")
    assert [r.offer.code for r in rank_offers(candidates(twin1, twin2), Context(), NOW, 5)] == ["TWIN-A", "TWIN-B"]


def test_rank_limit_and_discount_preview():
    many = [offer(id=str(i), code=f"C{i:02d}") for i in range(8)]
    assert len(rank_offers(candidates(*many), Context(), NOW, limit=3)) == 3
    ranked = rank_offers(candidates(offer(value=10, max_discount=50)), Context(order_value=1000), NOW, 5)
    assert ranked[0].discount_preview == 50.0
    free = rank_offers(candidates(offer(offer_type="free_shipping", value=0)), Context(), NOW, 5)
    assert free[0].free_shipping is True and free[0].discount_preview is None


def test_rank_scores_stay_between_0_and_1():
    wild = offer(value=10**6, priority=10**6, ends_at=NOW + timedelta(seconds=1), target_segments=("champions",),
                 target_categories=("Laptops",))
    ranked = rank_offers(candidates(wild), Context(segment="champions", favorite_category="Laptops"), NOW, 5)
    assert 0 < ranked[0].score <= 1.0
