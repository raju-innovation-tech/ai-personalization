"""Customer segments produced by RFM scoring (see app.customers.intelligence)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SegmentDef:
    key: str
    name: str
    description: str
    action: str


SEGMENTS: tuple[SegmentDef, ...] = (
    SegmentDef("champions", "Champions",
               "Bought recently, buy often and spend the most.",
               "Reward them: early access, loyalty perks, ask for reviews."),
    SegmentDef("loyal", "Loyal Customers",
               "Order regularly and respond well to offers.",
               "Upsell higher-value products and offer a loyalty programme."),
    SegmentDef("potential_loyalist", "Potential Loyalists",
               "Recent buyers who have not yet formed a habit.",
               "Recommend related products and offer a membership."),
    SegmentDef("new_customer", "New Customers",
               "Placed their first order recently.",
               "Welcome series and an incentive for the second purchase."),
    SegmentDef("need_attention", "Need Attention",
               "Above-average buyers who have not ordered for a while.",
               "Limited-time offers and personalised recommendations."),
    SegmentDef("about_to_sleep", "About To Sleep",
               "Below-average recency and frequency; starting to drift away.",
               "Share popular products and a gentle discount to re-engage."),
    SegmentDef("cant_lose", "Can't Lose Them",
               "Used to be top customers but have gone quiet.",
               "Win back with a personal message and a strong offer."),
    SegmentDef("at_risk", "At Risk",
               "Ordered often before but have not returned recently.",
               "Send reactivation offers and ask for feedback."),
    SegmentDef("hibernating", "Hibernating",
               "Low recency and low frequency.",
               "Low-cost reactivation; otherwise keep out of paid campaigns."),
    SegmentDef("lost", "Lost",
               "Lowest recency, frequency and spend.",
               "Revive only with very low-cost campaigns."),
    SegmentDef("prospect", "Prospects",
               "Active recently but have never purchased.",
               "Cart reminders and a first-order incentive."),
    SegmentDef("inactive", "Inactive Browsers",
               "Never purchased and not seen recently.",
               "Occasional re-engagement; do not over-invest."),
)

SEGMENT_BY_KEY: dict[str, SegmentDef] = {s.key: s for s in SEGMENTS}
SEGMENT_KEYS: tuple[str, ...] = tuple(s.key for s in SEGMENTS)
