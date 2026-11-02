"""
Offer engine (Phase 4) - pure Python, no database or web code.

* effective_status : draft / scheduled / active / expired / paused / ended
* check_eligibility: why (or why not) a customer may use an offer right now
* compute_discount : the discount for an order value, honouring max_discount
* rank_offers      : personalised ordering of the offers a customer can use
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

OFFER_TYPES = ("percent_off", "fixed_off", "free_shipping")
STATUSES = ("draft", "active", "paused", "ended")

# Human readable text for every reason an offer can be refused.
REASON_MESSAGES: dict[str, str] = {
    "OFFER_NOT_FOUND": "No offer with this code exists.",
    "NOT_ACTIVE": "This offer is not active.",
    "NOT_STARTED": "This offer has not started yet.",
    "EXPIRED": "This offer has expired.",
    "NOT_ELIGIBLE": "This offer is not available for this customer.",
    "LIMIT_REACHED": "This offer has reached its redemption limit.",
    "CUSTOMER_LIMIT_REACHED": "The customer has already used this offer the maximum number of times.",
    "MIN_ORDER_NOT_MET": "The order value is below the minimum for this offer.",
    "CATEGORY_NOT_MATCHED": "The cart does not contain a product category this offer applies to.",
}


@dataclass(frozen=True)
class OfferRule:
    """Everything the engine needs to know about one offer."""

    id: str
    code: str
    name: str
    offer_type: str
    value: float
    status: str
    description: str | None = None
    max_discount: float | None = None
    min_order_value: float | None = None
    max_redemptions: int | None = None
    max_per_customer: int = 1
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    target_segments: tuple[str, ...] = ()
    target_categories: tuple[str, ...] = ()
    priority: int = 50


@dataclass(frozen=True)
class Usage:
    """How much of an offer has been used (loaded from the database)."""

    total_redemptions: int = 0
    customer_redemptions: int = 0
    impressions: int = 0


@dataclass(frozen=True)
class Context:
    """Who is asking, and what they are doing."""

    segment: str | None = None
    segment_name: str | None = None
    favorite_category: str | None = None
    order_value: float | None = None
    categories: tuple[str, ...] = ()  # categories in the cart (checkout)
    browsing_category: str | None = None  # category being browsed (storefront)
    checkout: bool = False  # validate / redeem: category targeting is then mandatory


@dataclass(frozen=True)
class Ranked:
    offer: OfferRule
    score: float
    reason: str
    discount_preview: float | None = None
    free_shipping: bool = False


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _lower(values) -> set[str]:
    return {str(v).strip().lower() for v in values if str(v).strip()}


def effective_status(offer: OfferRule, now: datetime) -> str:
    """The stored status, refined by the schedule: scheduled / expired are derived."""
    if offer.status != "active":
        return offer.status
    starts, ends = _aware(offer.starts_at), _aware(offer.ends_at)
    if ends is not None and now >= ends:
        return "expired"
    if starts is not None and now < starts:
        return "scheduled"
    return "active"


def check_eligibility(offer: OfferRule, usage: Usage, ctx: Context, now: datetime) -> str | None:
    """None when the customer can use the offer, otherwise a reason code (see REASON_MESSAGES)."""
    status = effective_status(offer, now)
    if status == "scheduled":
        return "NOT_STARTED"
    if status == "expired":
        return "EXPIRED"
    if status != "active":
        return "NOT_ACTIVE"

    if offer.target_segments and ctx.segment not in offer.target_segments:
        return "NOT_ELIGIBLE"
    if offer.max_redemptions is not None and usage.total_redemptions >= offer.max_redemptions:
        return "LIMIT_REACHED"
    if usage.customer_redemptions >= offer.max_per_customer:
        return "CUSTOMER_LIMIT_REACHED"
    if offer.min_order_value and ctx.order_value is not None and ctx.order_value < offer.min_order_value:
        return "MIN_ORDER_NOT_MET"

    if offer.target_categories:
        wanted = _lower(offer.target_categories)
        if ctx.checkout:
            if not (_lower(ctx.categories) & wanted):
                return "CATEGORY_NOT_MATCHED"
        elif ctx.browsing_category is not None and ctx.browsing_category.strip().lower() not in wanted:
            return "CATEGORY_NOT_MATCHED"
    return None


def compute_discount(offer: OfferRule, order_value: float | None) -> tuple[float, bool]:
    """Returns (discount_amount, free_shipping). The discount never exceeds the order or max_discount."""
    total = max(order_value or 0.0, 0.0)
    if offer.offer_type == "free_shipping":
        return 0.0, True
    if offer.offer_type == "percent_off":
        amount = total * offer.value / 100.0
    elif offer.offer_type == "fixed_off":
        amount = min(offer.value, total)
    else:
        amount = 0.0
    if offer.max_discount is not None:
        amount = min(amount, offer.max_discount)
    return round(max(amount, 0.0), 2), False


def _score(offer: OfferRule, usage: Usage, ctx: Context, now: datetime) -> tuple[float, str]:
    explicit_segment = bool(offer.target_segments) and ctx.segment in offer.target_segments
    category_match = bool(
        offer.target_categories
        and ctx.favorite_category
        and ctx.favorite_category.strip().lower() in _lower(offer.target_categories)
    )

    relevance = 1.0 if explicit_segment else 0.4
    if category_match:
        relevance = min(1.0, relevance + 0.3)

    if offer.offer_type == "percent_off":
        value = min(offer.value, 50.0) / 50.0
    elif offer.offer_type == "fixed_off":
        value = min(offer.value / ctx.order_value, 0.5) / 0.5 if ctx.order_value else 0.5
    else:
        value = 0.4

    priority = max(0, min(offer.priority, 100)) / 100.0

    urgency, days_left = 0.0, None
    ends = _aware(offer.ends_at)
    if ends is not None:
        days_left = max((ends - now).total_seconds() / 86400.0, 0.0)
        urgency = max(0.0, 1.0 - days_left / 7.0)

    conversion = (usage.total_redemptions + 1) / (usage.impressions + 20)
    performance = min(conversion / 0.2, 1.0)

    score = 0.35 * relevance + 0.25 * value + 0.20 * priority + 0.10 * urgency + 0.10 * performance

    if explicit_segment:
        reason = f"Made for {ctx.segment_name or ctx.segment}"
    elif category_match:
        reason = f"Matches your interest in {ctx.favorite_category}"
    elif days_left is not None and days_left <= 3:
        reason = "Ends soon" if days_left < 1 else f"Ends in {math.ceil(days_left)} days"
    elif offer.offer_type == "percent_off" and offer.value >= 25:
        reason = "Big saving"
    else:
        reason = "Available for you"
    return round(score, 4), reason


def rank_offers(
    candidates: list[tuple[OfferRule, Usage]], ctx: Context, now: datetime, limit: int
) -> list[Ranked]:
    """Eligible offers only, best first (ties broken by code so results are stable)."""
    ranked: list[Ranked] = []
    for offer, usage in candidates:
        if check_eligibility(offer, usage, ctx, now) is not None:
            continue
        score, reason = _score(offer, usage, ctx, now)
        preview, free_shipping = (None, offer.offer_type == "free_shipping")
        if ctx.order_value is not None:
            preview, free_shipping = compute_discount(offer, ctx.order_value)
        ranked.append(Ranked(offer, score, reason, preview, free_shipping))
    ranked.sort(key=lambda r: (-r.score, r.offer.code))
    return ranked[:limit]
