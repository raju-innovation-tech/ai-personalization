"""
Recommendation engine (Phase 2) - pure Python, no ML dependencies.

A `Snapshot` is an immutable in-memory model built from the catalog and the
recent behaviour events. All recommendation strategies read from it:

* popularity      - time-decayed, weighted interaction counts
* content-based   - TF-IDF-weighted cosine similarity over category, brand,
                    tags, price band, colour and name tokens
* collaborative   - item-item cosine similarity over the implicit-feedback
                    user x item matrix, with shrinkage for few common users
* bought-together - basket co-occurrence (purchases in the same session)
* hybrid          - personalised blend of the above for one customer

The module has no database or web dependencies so it is easy to unit test;
`app.recommendations.service` is responsible for loading the data.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

# Importance of each behaviour for "how much does this customer like this
# product". Negative signals reduce interest (clamped at zero afterwards).
EVENT_WEIGHTS: dict[str, float] = {
    "PRODUCT_VIEW": 1.0,
    "WISHLIST_ADD": 3.0,
    "ADD_TO_CART": 4.0,
    "CHECKOUT_STARTED": 2.0,
    "PURCHASE": 8.0,
    "PRODUCT_REVIEW": 2.0,
    "RECOMMENDATION_CLICK": 2.0,
    "OFFER_CLICK": 1.0,
    "REMOVE_FROM_CART": -2.0,
    "WISHLIST_REMOVE": -3.0,
    "PURCHASE_CANCELLED": -8.0,
    "RETURN": -6.0,
}

USER_ITEM_CAP = 24.0  # one customer cannot dominate with endless repeat views
CF_SHRINKAGE = 3.0  # sim *= common / (common + CF_SHRINKAGE)
TOP_ITEMS_PER_USER = 10
NEIGHBORS_PER_ITEM = 30
MAX_BASKET_SIZE = 30

_TOKEN_RE = re.compile(r"[a-z0-9]{3,}")


@dataclass(slots=True)
class ProductInfo:
    product_id: str
    name: str
    category: str | None = None
    brand: str | None = None
    price: float | None = None
    image_url: str | None = None
    rating: float | None = None
    in_stock: bool = True
    is_active: bool = True
    tags: tuple[str, ...] = ()
    color: str | None = None


@dataclass(slots=True)
class Scored:
    product_id: str
    score: float
    reason: str
    algorithm: str  # popular | content | collaborative | fbt | hybrid


def _normalize(scores: dict[str, float]) -> dict[str, float]:
    """Scale so the best candidate is 1.0 (empty / all-zero stays empty)."""
    if not scores:
        return {}
    top = max(scores.values())
    if top <= 0:
        return {}
    return {k: v / top for k, v in scores.items() if v > 0}


def _top(scores: dict[str, float], k: int) -> list[tuple[str, float]]:
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:k]


class Snapshot:
    """Immutable recommendation model. Build with `Snapshot.build(...)`."""

    def __init__(self) -> None:
        self.built_at: datetime = datetime.now(timezone.utc)
        self.exclude_out_of_stock = True
        self.products: dict[str, ProductInfo] = {}
        self.user_items: dict[str, dict[str, float]] = {}
        self.item_users: dict[str, dict[str, float]] = {}
        self.item_norm: dict[str, float] = {}
        self.user_purchased: dict[str, set[str]] = {}
        self.popularity: dict[str, float] = {}
        self.vectors: dict[str, dict[str, float]] = {}
        self.postings: dict[str, list[tuple[str, float]]] = {}
        self.fbt: dict[str, list[tuple[str, int, float]]] = {}
        self.interaction_count = 0
        self.basket_count = 0
        self.fbt_pair_count = 0
        self._cf_cache: dict[str, list[tuple[str, float]]] = {}
        self._content_cache: dict[str, list[tuple[str, float]]] = {}

    # ------------------------------------------------------------------ build
    @classmethod
    def build(
        cls,
        products: Iterable[ProductInfo],
        interactions: Iterable[tuple[str, str, str, float]],
        basket_rows: Iterable[tuple[str, str, str]] = (),
        *,
        exclude_out_of_stock: bool = True,
        fbt_min_support: int = 2,
    ) -> "Snapshot":
        """
        products      - the catalog
        interactions  - (user_id, product_id, event_type, decayed_count) rows,
                        already time-decayed (1.0 == one event right now)
        basket_rows   - distinct (user_id, session_key, product_id) PURCHASE rows
        """
        snap = cls()
        snap.exclude_out_of_stock = exclude_out_of_stock
        snap.products = {p.product_id: p for p in products}

        snap._build_interactions(interactions)
        snap._build_content()
        snap._build_fbt(basket_rows, fbt_min_support)
        return snap

    def _build_interactions(self, interactions: Iterable[tuple[str, str, str, float]]) -> None:
        raw_user_item: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        raw_pop: dict[str, float] = defaultdict(float)
        purchased: dict[str, set[str]] = defaultdict(set)

        for user_id, product_id, event_type, decayed in interactions:
            if product_id not in self.products:
                continue  # event for a product that is not (or no longer) in the catalog
            weight = EVENT_WEIGHTS.get(event_type)
            if weight is None:
                continue
            self.interaction_count += 1
            raw_user_item[user_id][product_id] += weight * decayed
            raw_pop[product_id] += weight * decayed
            if event_type == "PURCHASE" and decayed > 0:
                purchased[user_id].add(product_id)

        for user_id, items in raw_user_item.items():
            cleaned = {p: min(w, USER_ITEM_CAP) for p, w in items.items() if w > 0}
            if cleaned:
                self.user_items[user_id] = cleaned
                for product_id, w in cleaned.items():
                    self.item_users.setdefault(product_id, {})[user_id] = w

        for product_id, users in self.item_users.items():
            self.item_norm[product_id] = math.sqrt(sum(w * w for w in users.values()))

        self.user_purchased = dict(purchased)

        positive = {p: math.log1p(v) for p, v in raw_pop.items() if v > 0}
        top = max(positive.values()) if positive else 0.0
        self.popularity = {p: v / top for p, v in positive.items()} if top > 0 else {}

    def _features(self, product: ProductInfo) -> dict[str, float]:
        features: dict[str, float] = {}
        if product.category:
            features[f"cat:{product.category.lower()}"] = 3.0
        if product.brand:
            features[f"brand:{product.brand.lower()}"] = 1.5
        for tag in product.tags:
            features[f"tag:{str(tag).lower()}"] = 1.0
        if product.price and product.price > 0:
            features[f"price:{int(math.log2(product.price))}"] = 0.8
        if product.color:
            features[f"color:{product.color.lower()}"] = 0.5
        skip = set(_TOKEN_RE.findall(f"{product.brand or ''} {product.category or ''}".lower()))
        for token in set(_TOKEN_RE.findall(product.name.lower())):
            if token not in skip:
                features[f"tok:{token}"] = 0.5
        return features

    def _build_content(self) -> None:
        raw = {pid: self._features(p) for pid, p in self.products.items()}
        doc_freq: dict[str, int] = defaultdict(int)
        for feats in raw.values():
            for name in feats:
                doc_freq[name] += 1
        n = max(len(raw), 1)

        postings: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for pid, feats in raw.items():
            weighted = {
                name: w * (math.log((n + 1) / (doc_freq[name] + 1)) + 1.0) for name, w in feats.items()
            }
            norm = math.sqrt(sum(v * v for v in weighted.values()))
            if norm == 0:
                continue
            vector = {name: v / norm for name, v in weighted.items()}
            self.vectors[pid] = vector
            for name, v in vector.items():
                postings[name].append((pid, v))
        self.postings = dict(postings)

    def _build_fbt(self, basket_rows: Iterable[tuple[str, str, str]], min_support: int) -> None:
        baskets: dict[tuple[str, str], set[str]] = defaultdict(set)
        for user_id, session_key, product_id in basket_rows:
            if product_id in self.products:
                baskets[(user_id, session_key)].add(product_id)
        self.basket_count = len(baskets)

        item_baskets: dict[str, int] = defaultdict(int)
        pair_counts: dict[tuple[str, str], int] = defaultdict(int)
        for items in baskets.values():
            for item in items:
                item_baskets[item] += 1
            if 2 <= len(items) <= MAX_BASKET_SIZE:
                ordered = sorted(items)
                for i, a in enumerate(ordered):
                    for b in ordered[i + 1 :]:
                        pair_counts[(a, b)] += 1

        neighbours: dict[str, list[tuple[str, int, float]]] = defaultdict(list)
        for (a, b), support in pair_counts.items():
            if support < min_support:
                continue
            score = support / math.sqrt(item_baskets[a] * item_baskets[b])
            neighbours[a].append((b, support, score))
            neighbours[b].append((a, support, score))
            self.fbt_pair_count += 1
        self.fbt = {
            a: sorted(rows, key=lambda r: (-r[2], -r[1], r[0])) for a, rows in neighbours.items()
        }

    # -------------------------------------------------------------- neighbours
    def content_neighbors(self, product_id: str, k: int = NEIGHBORS_PER_ITEM) -> list[tuple[str, float]]:
        cached = self._content_cache.get(product_id)
        if cached is not None:
            return cached[:k]
        vector = self.vectors.get(product_id)
        if not vector:
            return []
        scores: dict[str, float] = defaultdict(float)
        for name, w in vector.items():
            for other, ow in self.postings.get(name, ()):
                if other != product_id:
                    scores[other] += w * ow
        result = _top(scores, 100)
        self._content_cache[product_id] = result
        return result[:k]

    def cf_neighbors(self, product_id: str, k: int = NEIGHBORS_PER_ITEM) -> list[tuple[str, float]]:
        cached = self._cf_cache.get(product_id)
        if cached is not None:
            return cached[:k]
        users = self.item_users.get(product_id)
        if not users:
            return []
        dots: dict[str, float] = defaultdict(float)
        common: dict[str, int] = defaultdict(int)
        for user_id, w_i in users.items():
            for other, w_j in self.user_items[user_id].items():
                if other != product_id:
                    dots[other] += w_i * w_j
                    common[other] += 1
        norm_i = self.item_norm[product_id]
        scores = {
            other: (dot / (norm_i * self.item_norm[other])) * (common[other] / (common[other] + CF_SHRINKAGE))
            for other, dot in dots.items()
            if self.item_norm.get(other)
        }
        result = _top(scores, 100)
        self._cf_cache[product_id] = result
        return result[:k]

    # ------------------------------------------------------------------ helpers
    def eligible(self, product_id: str) -> bool:
        product = self.products.get(product_id)
        if product is None or not product.is_active:
            return False
        if self.exclude_out_of_stock and not product.in_stock:
            return False
        return True

    def _name(self, product_id: str) -> str:
        product = self.products.get(product_id)
        return product.name if product else product_id

    def _diversify(self, ranked: list[Scored], limit: int, max_per_category: int) -> list[Scored]:
        """Prefer a mix of categories; only exceed the cap if we'd run out of items."""
        picked: list[Scored] = []
        leftovers: list[Scored] = []
        per_category: dict[str | None, int] = defaultdict(int)
        for item in ranked:
            category = self.products[item.product_id].category
            if per_category[category] < max_per_category:
                picked.append(item)
                per_category[category] += 1
            else:
                leftovers.append(item)
            if len(picked) >= limit:
                return picked
        return (picked + leftovers)[:limit]

    # ---------------------------------------------------------------- strategies
    def popular(
        self,
        limit: int,
        *,
        category: str | None = None,
        exclude: set[str] | None = None,
        reason: str = "Trending right now",
    ) -> list[Scored]:
        exclude = exclude or set()
        wanted = category.lower() if category else None
        ranked = _top(self.popularity, len(self.popularity))
        out: list[Scored] = []
        for product_id, score in ranked:
            if product_id in exclude or not self.eligible(product_id):
                continue
            if wanted and (self.products[product_id].category or "").lower() != wanted:
                continue
            out.append(Scored(product_id, round(score, 4), reason, "popular"))
            if len(out) >= limit:
                break
        if len(out) < limit:
            # Catalog items with no interactions yet: best-rated first so a fresh
            # system still returns something sensible.
            seen = {s.product_id for s in out} | exclude
            rest = [
                p
                for p in self.products.values()
                if p.product_id not in seen
                and self.eligible(p.product_id)
                and (not wanted or (p.category or "").lower() == wanted)
            ]
            rest.sort(key=lambda p: (-(p.rating or 0.0), p.product_id))
            for p in rest[: limit - len(out)]:
                out.append(Scored(p.product_id, 0.0, reason, "popular"))
        return out

    def similar(self, product_id: str, limit: int) -> list[Scored]:
        content = _normalize(dict(self.content_neighbors(product_id, 100)))
        cf = _normalize(dict(self.cf_neighbors(product_id, 100)))
        w_content, w_cf = (0.65, 0.35) if cf else (1.0, 0.0)

        ranked: list[Scored] = []
        for other in set(content) | set(cf):
            if not self.eligible(other):
                continue
            c, f = w_content * content.get(other, 0.0), w_cf * cf.get(other, 0.0)
            if f > c:
                algorithm, reason = "collaborative", "Customers who viewed this also viewed"
            else:
                algorithm, reason = "content", "Similar category, brand and style"
            ranked.append(Scored(other, round(c + f, 4), reason, algorithm))
        ranked.sort(key=lambda s: (-s.score, s.product_id))
        out = ranked[:limit]
        if len(out) < limit:
            category = self.products[product_id].category if product_id in self.products else None
            taken = {s.product_id for s in out} | {product_id}
            out += self.popular(limit - len(out), category=category, exclude=taken)
            if len(out) < limit:
                taken = {s.product_id for s in out} | {product_id}
                out += self.popular(limit - len(out), exclude=taken)
        return out

    def frequently_bought_together(self, product_id: str, limit: int) -> list[Scored]:
        out: list[Scored] = []
        for other, support, score in self.fbt.get(product_id, ()):
            if not self.eligible(other):
                continue
            out.append(
                Scored(other, round(score, 4), f"Bought together in {support} orders", "fbt")
            )
            if len(out) >= limit:
                return out
        # Not enough basket data for this product: fall back to what similar shoppers liked.
        taken = {s.product_id for s in out} | {product_id}
        for item in self.cf_neighbors(product_id, limit * 3):
            other, score = item
            if len(out) >= limit:
                break
            if other in taken or not self.eligible(other):
                continue
            out.append(Scored(other, round(score, 4), "Popular with similar shoppers", "collaborative"))
            taken.add(other)
        return out

    def has_history(self, user_id: str) -> bool:
        return bool(self.user_items.get(user_id))

    def for_user(self, user_id: str, limit: int, strategy: str = "hybrid") -> tuple[list[Scored], str]:
        """
        Personalised list for one customer. Returns (items, algorithm).

        strategy (used by A/B tests): 'hybrid' (default blend), 'content' (similar-to-what-you-viewed only),
        'collaborative' (customers-like-you only) or 'popular' (not personalised). A customer with no
        history always gets 'popular' (cold start).
        """
        interests = self.user_items.get(user_id)
        purchased = self.user_purchased.get(user_id, set())
        if not interests or strategy == "popular":
            return self.popular(limit, exclude=purchased), "popular"

        top_items = _top(interests, TOP_ITEMS_PER_USER)
        total_weight = sum(w for _, w in top_items) or 1.0

        cf_scores: dict[str, float] = defaultdict(float)
        content_scores: dict[str, float] = defaultdict(float)
        cf_source: dict[str, tuple[float, str]] = {}
        content_source: dict[str, tuple[float, str]] = {}

        for item, weight in top_items:
            relative = weight / total_weight
            for other, sim in self.cf_neighbors(item):
                contribution = relative * sim
                cf_scores[other] += contribution
                if contribution > cf_source.get(other, (0.0, ""))[0]:
                    cf_source[other] = (contribution, item)
            for other, sim in self.content_neighbors(item):
                contribution = relative * sim
                content_scores[other] += contribution
                if contribution > content_source.get(other, (0.0, ""))[0]:
                    content_source[other] = (contribution, item)

        cf_n, content_n = _normalize(cf_scores), _normalize(content_scores)
        if strategy == "content":
            cf_n = {}
        elif strategy == "collaborative" and cf_n:
            content_n = {}
        base_weights = {"content": (0.0, 0.8, 0.2), "collaborative": (0.8, 0.0, 0.2)}.get(strategy, (0.5, 0.3, 0.2))
        w_cf, w_content, w_pop = base_weights if cf_n else (0.0, 0.75, 0.25)

        ranked: list[Scored] = []
        for other in set(cf_n) | set(content_n):
            if other in purchased or not self.eligible(other):
                continue
            c_part = w_cf * cf_n.get(other, 0.0)
            t_part = w_content * content_n.get(other, 0.0)
            score = c_part + t_part + w_pop * self.popularity.get(other, 0.0)
            if c_part >= t_part and other in cf_source:
                algorithm = "collaborative"
                reason = f"Customers who liked {self._name(cf_source[other][1])} also liked this"
            else:
                algorithm = "content"
                source = content_source.get(other, (0.0, top_items[0][0]))[1]
                reason = f"Similar to {self._name(source)}, which you viewed"
            ranked.append(Scored(other, round(score, 4), reason, algorithm))
        ranked.sort(key=lambda s: (-s.score, s.product_id))

        out = self._diversify(ranked, limit, max_per_category=max(2, math.ceil(limit / 3)))
        if len(out) < limit:
            taken = {s.product_id for s in out} | purchased
            out += self.popular(limit - len(out), exclude=taken)
        return out, strategy if strategy in ("content", "collaborative") else "hybrid"

    def top_category(self, user_id: str) -> str | None:
        """The category this customer shows most interest in (for the home feed)."""
        interests = self.user_items.get(user_id)
        if not interests:
            return None
        totals: dict[str, float] = defaultdict(float)
        for product_id, weight in interests.items():
            category = self.products[product_id].category
            if category:
                totals[category] += weight
        return max(totals, key=lambda c: (totals[c], c)) if totals else None
