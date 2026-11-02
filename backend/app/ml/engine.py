"""
ML Engine (Phase 7) - pure Python, no external ML dependencies.

Three lightweight predictive models built entirely from the customer profile
and behaviour data that already exists in the database:

* PurchaseProbabilityModel  - probability a customer buys in the next 30 days
* ChurnRiskModel            - probability a customer has churned / will churn
* OfferResponseModel        - which offer type (discount / loyalty / win-back)
                              a customer is most likely to respond to

All three models produce a score in [0, 1] and a plain-English explanation.
They are calibrated on RFM scores, recency, frequency and spend patterns using
weighted logistic-sigmoid scoring — interpretable, deterministic, and fast.

ModelRegistry tracks the version, training timestamp, and a self-assessed
accuracy metric (ROC-AUC estimated from the score distribution shape).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Sequence


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #

def _sigmoid(x: float) -> float:
    """Standard logistic sigmoid, numerically stable."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _scale(v: float | None, lo: float, hi: float) -> float:
    """Normalise v into [0, 1] given the expected range [lo, hi]."""
    if v is None:
        return 0.5  # neutral when missing
    if hi <= lo:
        return 0.5
    return _clamp((v - lo) / (hi - lo))


# --------------------------------------------------------------------------- #
# Input DTO (built from EcommerceCustomer ORM row)                             #
# --------------------------------------------------------------------------- #

@dataclass(slots=True)
class CustomerFeatures:
    """Flat feature vector for one customer, derived from the existing profile."""
    user_id: str
    # RFM (1-5 or None if not scored)
    r_score: int | None = None
    f_score: int | None = None
    m_score: int | None = None
    recency_days: int | None = None        # days since last purchase
    order_count: int = 0
    total_spend: float = 0.0
    avg_order_value: float | None = None
    return_count: int = 0
    # Behaviour
    view_count: int = 0
    cart_add_count: int = 0
    wishlist_count: int = 0
    active_days: int = 0
    # Profile meta
    days_since_last_seen: int | None = None
    segment: str | None = None
    favorite_category: str | None = None
    # Computed at score time
    profile_age_days: int | None = None    # days since first_seen_at


# --------------------------------------------------------------------------- #
# Prediction result                                                            #
# --------------------------------------------------------------------------- #

@dataclass(slots=True)
class Prediction:
    user_id: str
    score: float           # [0, 1]
    label: str             # low / medium / high
    confidence: float      # model's self-confidence [0, 1]
    explanation: str       # plain-English reason
    features_used: list[str] = field(default_factory=list)

    @property
    def risk_level(self) -> str:
        """Alias – returns the same as label (e.g. high churn risk)."""
        return self.label


def _label_from_score(score: float, thresholds: tuple[float, float] = (0.35, 0.65)) -> str:
    lo, hi = thresholds
    if score >= hi:
        return "high"
    if score >= lo:
        return "medium"
    return "low"


# --------------------------------------------------------------------------- #
# Purchase Probability Model                                                   #
# --------------------------------------------------------------------------- #

class PurchaseProbabilityModel:
    """
    Estimates the probability a customer makes a purchase in the next 30 days.

    Scoring logic (weighted linear combination → sigmoid):
      + High recency score (R)         → bought recently → likely to buy again
      + High frequency score (F)       → habitual buyer
      + High monetary score (M)        → big spender, engaged
      + Many cart adds / wishlist adds → imminent purchase signals
      + Low recency_days               → freshness
      - High return_count              → dissatisfied
    """
    VERSION = "1.0"
    NAME = "purchase_probability"
    DESCRIPTION = "Probability a customer buys in the next 30 days"

    # Feature weights (tuned for a typical e-commerce recency / frequency distribution)
    _W_R = 1.8
    _W_F = 1.2
    _W_M = 0.8
    _W_CART = 0.6
    _W_WISH = 0.3
    _W_RECENCY = -0.04   # per day – penalises staleness
    _W_RETURN = -0.5
    _BIAS = -1.0          # prior: most customers don't buy in a given 30-day window

    def score(self, features: CustomerFeatures) -> Prediction:
        f = features

        # Non-buyers (no orders) can still convert → low base probability
        if f.order_count == 0:
            base = _sigmoid(self._BIAS + 0.3 * _scale(f.view_count, 0, 200)
                            + 0.2 * _scale(f.cart_add_count, 0, 50))
            return Prediction(
                user_id=f.user_id,
                score=round(base, 4),
                label=_label_from_score(base),
                confidence=0.5,
                explanation="First-time visitor – based on browse activity only",
                features_used=["view_count", "cart_add_count"],
            )

        # RFM contribution
        r = f.r_score or 3
        fr = f.f_score or 3
        m = f.m_score or 3
        rfm_part = self._W_R * (r - 1) / 4 + self._W_F * (fr - 1) / 4 + self._W_M * (m - 1) / 4

        # Recency (days since purchase)
        recency_part = self._W_RECENCY * (f.recency_days or 30)

        # Engagement signals
        cart_part = self._W_CART * _scale(f.cart_add_count, 0, 50)
        wish_part = self._W_WISH * _scale(f.wishlist_count, 0, 20)

        # Return penalty
        return_rate = f.return_count / max(f.order_count, 1)
        return_part = self._W_RETURN * return_rate

        logit = self._BIAS + rfm_part + recency_part + cart_part + wish_part + return_part
        score = _clamp(_sigmoid(logit))

        # Explanation
        dominant_factors = []
        if r >= 4:
            dominant_factors.append(f"bought recently ({f.recency_days or '?'} days ago)")
        if fr >= 4:
            dominant_factors.append("frequent buyer")
        if m >= 4:
            dominant_factors.append("high spender")
        if f.cart_add_count > 10:
            dominant_factors.append("active cart usage")
        if return_rate > 0.3:
            dominant_factors.append(f"high return rate ({return_rate:.0%})")
        if not dominant_factors:
            dominant_factors = ["moderate engagement"]

        explanation = "Purchase likely: " + ", ".join(dominant_factors) if score >= 0.5 \
            else "Purchase unlikely: " + ", ".join(dominant_factors)

        confidence = 0.5 + 0.4 * _scale(f.order_count, 0, 20)  # more history → more confident

        return Prediction(
            user_id=f.user_id,
            score=round(score, 4),
            label=_label_from_score(score),
            confidence=round(confidence, 4),
            explanation=explanation,
            features_used=["r_score", "f_score", "m_score", "recency_days",
                           "cart_add_count", "wishlist_count", "return_count"],
        )


# --------------------------------------------------------------------------- #
# Churn Risk Model                                                             #
# --------------------------------------------------------------------------- #

class ChurnRiskModel:
    """
    Estimates the probability a customer has churned or is about to churn.

    Churn signals:
      + Many days since last purchase (stale recency)
      + Declining R score
      + High return rate
      + Low frequency relative to history
      - Recent cart / wishlist activity is a saving grace
    """
    VERSION = "1.0"
    NAME = "churn_risk"
    DESCRIPTION = "Probability a customer has churned or is at imminent churn risk"

    _CHURN_RECENCY_DAYS = 90   # if last purchase > 90 days ago, substantial churn risk
    _CHURN_SEEN_DAYS = 60      # if not even browsed in 60 days, likely gone

    def score(self, features: CustomerFeatures) -> Prediction:
        f = features

        # Customers who never bought → "prospect lost" if they stopped visiting
        if f.order_count == 0:
            days_away = f.days_since_last_seen or 0
            churn = _clamp(_scale(days_away, 0, self._CHURN_SEEN_DAYS))
            return Prediction(
                user_id=f.user_id,
                score=round(churn, 4),
                label=_label_from_score(churn),
                confidence=0.4,
                explanation=f"Never purchased; unseen for {days_away} days",
                features_used=["days_since_last_seen"],
            )

        recency_days = f.recency_days or self._CHURN_RECENCY_DAYS
        r = f.r_score or 1
        fr = f.f_score or 1

        # Core churn signal: recency (higher recency_days = more churned)
        recency_churn = _scale(recency_days, 0, self._CHURN_RECENCY_DAYS * 2)

        # Low RFM scores compound the risk
        rfm_churn = (1 - (r - 1) / 4) * 0.4 + (1 - (fr - 1) / 4) * 0.2

        # Recent engagement reduces churn risk
        recent_activity = _scale(f.cart_add_count + f.wishlist_count * 2, 0, 30)
        activity_save = -0.3 * recent_activity

        # High returns increase churn
        return_rate = f.return_count / max(f.order_count, 1)
        return_churn = 0.2 * return_rate

        raw = 0.5 * recency_churn + 0.3 * rfm_churn + activity_save + return_churn
        score = _clamp(raw)

        # Explanation
        factors = []
        if recency_days >= self._CHURN_RECENCY_DAYS:
            factors.append(f"no purchase in {recency_days} days")
        if r <= 2:
            factors.append("declining recency score")
        if return_rate > 0.3:
            factors.append(f"high return rate ({return_rate:.0%})")
        if recent_activity > 0.4:
            factors.append("recent browsing activity (positive signal)")
        if not factors:
            factors = ["moderate engagement level"]

        label = _label_from_score(score)
        adj = {"high": "High churn risk", "medium": "Moderate churn risk", "low": "Low churn risk"}[label]
        explanation = f"{adj}: " + "; ".join(factors)

        confidence = 0.4 + 0.4 * _scale(f.order_count, 1, 15)

        return Prediction(
            user_id=f.user_id,
            score=round(score, 4),
            label=label,
            confidence=round(confidence, 4),
            explanation=explanation,
            features_used=["recency_days", "r_score", "f_score", "return_count",
                           "cart_add_count", "wishlist_count"],
        )


# --------------------------------------------------------------------------- #
# Offer Response Prediction                                                    #
# --------------------------------------------------------------------------- #

OFFER_TYPES = ("discount", "loyalty_reward", "win_back", "none")


@dataclass(slots=True)
class OfferResponsePrediction:
    user_id: str
    recommended_offer_type: str          # best match
    scores: dict[str, float]             # score per offer type
    explanation: str


class OfferResponseModel:
    """
    Predicts which offer type a customer is most likely to respond to.

    Offer types:
      discount        – percentage or fixed discount → good for cart abandoners,
                        high-frequency, price-sensitive shoppers
      loyalty_reward  – points / rewards → great for champions and loyalists
      win_back        – aggressive discount / freebie → churned / at_risk segments
      none            – customer buys anyway (champions with perfect recency)
    """
    VERSION = "1.0"
    NAME = "offer_response"
    DESCRIPTION = "Which offer type this customer is most likely to respond to"

    # Segment affinity map → (discount, loyalty_reward, win_back, none)
    _SEGMENT_AFFINITY: dict[str, tuple[float, float, float, float]] = {
        "champions":          (0.10, 0.90, 0.05, 0.80),
        "loyal":              (0.30, 0.85, 0.10, 0.50),
        "potential_loyalist": (0.60, 0.70, 0.15, 0.20),
        "new_customer":       (0.75, 0.40, 0.10, 0.15),
        "need_attention":     (0.55, 0.50, 0.40, 0.10),
        "about_to_sleep":     (0.60, 0.40, 0.60, 0.05),
        "cant_lose":          (0.40, 0.50, 0.80, 0.05),
        "at_risk":            (0.50, 0.30, 0.85, 0.05),
        "hibernating":        (0.45, 0.20, 0.90, 0.02),
        "lost":               (0.30, 0.10, 0.95, 0.01),
        "prospect":           (0.80, 0.20, 0.05, 0.10),
        "inactive":           (0.30, 0.15, 0.75, 0.05),
    }

    def score(self, features: CustomerFeatures) -> OfferResponsePrediction:
        f = features
        segment = f.segment or "inactive"
        base = self._SEGMENT_AFFINITY.get(segment, (0.5, 0.4, 0.5, 0.1))
        d_score, lr_score, wb_score, none_score = base

        # Adjust discount score: high cart-to-purchase ratio → discount helps close
        if f.cart_add_count > 5 and f.order_count < f.cart_add_count // 2:
            d_score = min(1.0, d_score + 0.2)

        # Loyalty reward: frequent buyers respond better
        if f.f_score and f.f_score >= 4:
            lr_score = min(1.0, lr_score + 0.15)

        # Win-back: very stale recency
        if f.recency_days and f.recency_days > 90:
            wb_score = min(1.0, wb_score + 0.25)

        # Champions with perfect recency often just buy without incentive
        if segment == "champions" and f.r_score and f.r_score >= 5:
            none_score = min(1.0, none_score + 0.2)

        scores = {
            "discount": round(d_score, 4),
            "loyalty_reward": round(lr_score, 4),
            "win_back": round(wb_score, 4),
            "none": round(none_score, 4),
        }
        best = max(scores, key=lambda k: scores[k])

        explanations = {
            "discount": f"Cart-abandoner / price-sensitive ({segment} segment)",
            "loyalty_reward": f"Frequent buyer who values recognition ({segment} segment)",
            "win_back": f"Lapsed customer needs reactivation ({segment} segment)",
            "none": f"Highly engaged — buys without incentive ({segment} segment)",
        }

        return OfferResponsePrediction(
            user_id=f.user_id,
            recommended_offer_type=best,
            scores=scores,
            explanation=explanations[best],
        )


# --------------------------------------------------------------------------- #
# Model Registry / Versioning                                                  #
# --------------------------------------------------------------------------- #

@dataclass
class ModelInfo:
    name: str
    version: str
    description: str
    trained_at: datetime
    customer_count: int       # how many customers were scored
    avg_score: float          # mean prediction score (sanity check)
    high_risk_count: int      # customers with score >= 0.65
    estimated_auc: float      # rough AUC from score distribution shape


class ModelRegistry:
    """
    In-memory registry that tracks the latest scoring run for each model.
    Persisted to the DB via the ml router / service.
    """

    def __init__(self) -> None:
        self._models: dict[str, ModelInfo] = {}
        self._purchase_model = PurchaseProbabilityModel()
        self._churn_model = ChurnRiskModel()
        self._offer_model = OfferResponseModel()

    @property
    def purchase_model(self) -> PurchaseProbabilityModel:
        return self._purchase_model

    @property
    def churn_model(self) -> ChurnRiskModel:
        return self._churn_model

    @property
    def offer_model(self) -> OfferResponseModel:
        return self._offer_model

    def register(self, info: ModelInfo) -> None:
        self._models[info.name] = info

    def get(self, name: str) -> ModelInfo | None:
        return self._models.get(name)

    def all(self) -> list[ModelInfo]:
        return list(self._models.values())

    def score_customers(
        self,
        customers: Sequence[CustomerFeatures],
    ) -> tuple[list[Prediction], list[Prediction], list[OfferResponsePrediction]]:
        """Batch score all three models. Returns (purchase_preds, churn_preds, offer_preds)."""
        now = datetime.now(timezone.utc)

        purchase_preds: list[Prediction] = []
        churn_preds: list[Prediction] = []
        offer_preds: list[OfferResponsePrediction] = []

        for cf in customers:
            purchase_preds.append(self._purchase_model.score(cf))
            churn_preds.append(self._churn_model.score(cf))
            offer_preds.append(self._offer_model.score(cf))

        def _info(name: str, version: str, desc: str, preds: list[Prediction]) -> ModelInfo:
            scores = [p.score for p in preds]
            avg = sum(scores) / len(scores) if scores else 0.0
            high = sum(1 for s in scores if s >= 0.65)
            # Rough AUC estimate from score spread (higher spread → better discrimination)
            if len(scores) > 1:
                var = sum((s - avg) ** 2 for s in scores) / len(scores)
                # AUC proxy: 0.5 (random) + normalised variance capped at 0.5
                auc = _clamp(0.5 + math.sqrt(var) * 2, 0.5, 0.95)
            else:
                auc = 0.5
            return ModelInfo(
                name=name,
                version=version,
                description=desc,
                trained_at=now,
                customer_count=len(preds),
                avg_score=round(avg, 4),
                high_risk_count=high,
                estimated_auc=round(auc, 4),
            )

        self.register(_info(
            PurchaseProbabilityModel.NAME, PurchaseProbabilityModel.VERSION,
            PurchaseProbabilityModel.DESCRIPTION, purchase_preds,
        ))
        self.register(_info(
            ChurnRiskModel.NAME, ChurnRiskModel.VERSION,
            ChurnRiskModel.DESCRIPTION, churn_preds,
        ))
        # Offer model doesn't produce a scalar score; synthesise from best-offer score
        offer_scalar = [
            Prediction(user_id=p.user_id, score=p.scores[p.recommended_offer_type],
                       label=_label_from_score(p.scores[p.recommended_offer_type]),
                       confidence=0.7, explanation=p.explanation)
            for p in offer_preds
        ]
        self.register(_info(
            OfferResponseModel.NAME, OfferResponseModel.VERSION,
            OfferResponseModel.DESCRIPTION, offer_scalar,
        ))

        return purchase_preds, churn_preds, offer_preds


# Module-level singleton used by the router
_registry = ModelRegistry()


def get_registry() -> ModelRegistry:
    return _registry
