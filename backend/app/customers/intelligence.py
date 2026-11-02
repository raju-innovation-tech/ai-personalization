"""
Customer intelligence (Phase 3) - pure Python, no database or web code.

* purchase_value  : how much one PURCHASE / RETURN event is worth
* score_quintiles : percentile-based 1-5 scoring (used for recency and monetary)
* score_frequency : fixed-bin 1-5 scoring of the order count
* assign_segment  : rule table that turns (R, F, M) into a named segment
* build_profiles  : CustomerStats -> profile dicts ready to be stored
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

MAX_QUANTITY = 1000


# --------------------------------------------------------------------- values
def _number(value) -> float | None:
    """Accept ints/floats/numeric strings; reject bools, NaN, inf and junk."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None


def purchase_quantity(metadata) -> int:
    meta = metadata if isinstance(metadata, dict) else {}
    quantity = _number(meta.get("quantity"))
    if quantity is None or quantity < 1:
        return 1
    return int(min(quantity, MAX_QUANTITY))


def purchase_value(metadata, catalog_price: float | None) -> float:
    """
    Value of one purchase event. Priority:
      1. metadata["amount"]            - the line total, used as-is
      2. metadata["price"] (or the catalog price) x metadata["quantity"] (default 1)
    Unknown product and no price in the event -> 0.0
    """
    meta = metadata if isinstance(metadata, dict) else {}
    amount = _number(meta.get("amount"))
    if amount is not None and amount >= 0:
        return round(amount, 2)
    unit = _number(meta.get("price"))
    if unit is None or unit < 0:
        unit = catalog_price
    if unit is None:
        return 0.0
    return round(unit * purchase_quantity(meta), 2)


# -------------------------------------------------------------------- scoring
def score_quintiles(values: list[float]) -> list[int]:
    """
    1-5 score where a higher value is better, based on rank position (0 = worst,
    n-1 = best). Equal values share the score of their lowest position, so the
    bottom group always scores 1 and the single best customer always scores 5,
    however few customers there are. If every value is equal there is nothing
    to rank on, so everybody gets a neutral 3.
    """
    n = len(values)
    if n == 0:
        return []
    if len(set(values)) == 1:
        return [3] * n
    order = sorted(range(n), key=lambda i: values[i])
    scores = [0] * n
    i = 0
    while i < n:
        j = i
        while j < n and values[order[j]] == values[order[i]]:
            j += 1
        score = min(5, int(5 * i / (n - 1)) + 1)  # n >= 2 here: all-equal input returned above
        for k in range(i, j):
            scores[order[k]] = score
        i = j
    return scores


def score_frequency(orders: int) -> int:
    """
    Frequency uses fixed bins, not percentiles: order counts are small whole
    numbers with huge ties (most customers have 1 order), so ranking them can
    only ever produce a few distinct scores.
        1 order -> 1,  2 -> 2,  3 -> 3,  4-5 -> 4,  6 or more -> 5
    """
    if orders >= 6:
        return 5
    if orders >= 4:
        return 4
    return max(1, orders)


def assign_segment(
    *,
    orders: int,
    recency_days: int | None,
    r: int | None,
    f: int | None,
    m: int | None,
    days_since_seen: int | None,
    active_days: int = 30,
) -> str:
    """First matching rule wins. Non-buyers are prospects or inactive browsers."""
    if orders <= 0 or r is None or f is None or m is None:
        recently_active = days_since_seen is not None and days_since_seen <= active_days
        return "prospect" if recently_active else "inactive"

    if orders == 1 and recency_days is not None and recency_days <= active_days:
        return "new_customer"
    if r >= 4 and f >= 4 and m >= 4:
        return "champions"
    if r <= 2 and f >= 4 and m >= 4:
        return "cant_lose"
    if f >= 4 and r >= 3:
        return "loyal"
    if r <= 2 and f >= 3:
        return "at_risk"
    if r == 3 and f >= 3:
        return "need_attention"
    if r >= 4:
        return "potential_loyalist"
    if r == 3:
        return "about_to_sleep"
    if r == 2:
        return "hibernating"
    return "lost"


# ------------------------------------------------------------------- profiles
@dataclass
class CustomerStats:
    user_id: str
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    total_events: int = 0
    views: int = 0
    cart_adds: int = 0
    wishlist_adds: int = 0
    active_days: int = 0
    orders: int = 0
    items: int = 0
    returns: int = 0
    spend: float = 0.0
    first_order: datetime | None = None
    last_order: datetime | None = None
    favorite_category: str | None = None
    favorite_brand: str | None = None


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def build_profiles(stats: list[CustomerStats], *, now: datetime, active_days: int = 30) -> list[dict]:
    """Add recency, RFM scores and the segment to every customer."""
    buyers = [s for s in stats if s.orders > 0 and s.last_order is not None]

    recency = {s.user_id: max(0, (now - _aware(s.last_order)).days) for s in buyers}  # type: ignore[arg-type]
    r_scores = dict(zip((s.user_id for s in buyers), score_quintiles([-recency[s.user_id] for s in buyers]), strict=True))
    f_scores = {s.user_id: score_frequency(s.orders) for s in buyers}
    m_scores = dict(zip((s.user_id for s in buyers), score_quintiles([round(s.spend, 2) for s in buyers]), strict=True))

    profiles: list[dict] = []
    for s in stats:
        is_buyer = s.user_id in recency
        r, f, m = r_scores.get(s.user_id), f_scores.get(s.user_id), m_scores.get(s.user_id)
        last_seen = _aware(s.last_seen)
        days_since_seen = max(0, (now - last_seen).days) if last_seen else None
        spend = round(max(s.spend, 0.0), 2)

        profiles.append(
            {
                "user_id": s.user_id,
                "first_seen_at": _aware(s.first_seen),
                "last_seen_at": last_seen,
                "total_events": s.total_events,
                "view_count": s.views,
                "cart_add_count": s.cart_adds,
                "wishlist_count": s.wishlist_adds,
                "active_days": s.active_days,
                "order_count": s.orders,
                "items_purchased": s.items,
                "return_count": s.returns,
                "total_spend": spend,
                "avg_order_value": round(spend / s.orders, 2) if s.orders > 0 else None,
                "first_order_at": _aware(s.first_order),
                "last_order_at": _aware(s.last_order),
                "recency_days": recency.get(s.user_id),
                "r_score": r,
                "f_score": f,
                "m_score": m,
                "rfm_code": f"{r}{f}{m}" if is_buyer else None,
                "segment": assign_segment(
                    orders=s.orders if is_buyer else 0,
                    recency_days=recency.get(s.user_id),
                    r=r,
                    f=f,
                    m=m,
                    days_since_seen=days_since_seen,
                    active_days=active_days,
                ),
                "favorite_category": s.favorite_category,
                "favorite_brand": s.favorite_brand,
                "profile_computed_at": now,
            }
        )
    return profiles


def segment_counts(profiles: list[dict]) -> dict[str, int]:
    return dict(Counter(p["segment"] for p in profiles))
