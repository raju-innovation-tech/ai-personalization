"""
Tests for the Phase 7 ML engine (pure Python, no database needed).
"""
import pytest

from app.ml.engine import (
    ChurnRiskModel,
    CustomerFeatures,
    ModelRegistry,
    OfferResponseModel,
    PurchaseProbabilityModel,
    _label_from_score,
    _sigmoid,
    get_registry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _buyer(
    *,
    user_id="TEST_USER",
    r_score=3,
    f_score=3,
    m_score=3,
    recency_days=20,
    order_count=5,
    total_spend=5000.0,
    return_count=0,
    cart_add_count=5,
    wishlist_count=2,
    days_since_last_seen=5,
    segment="loyal",
) -> CustomerFeatures:
    return CustomerFeatures(
        user_id=user_id,
        r_score=r_score,
        f_score=f_score,
        m_score=m_score,
        recency_days=recency_days,
        order_count=order_count,
        total_spend=total_spend,
        return_count=return_count,
        cart_add_count=cart_add_count,
        wishlist_count=wishlist_count,
        days_since_last_seen=days_since_last_seen,
        segment=segment,
    )


def _prospect(user_id="PROSPECT") -> CustomerFeatures:
    return CustomerFeatures(
        user_id=user_id,
        order_count=0,
        view_count=50,
        cart_add_count=3,
        days_since_last_seen=5,
        segment="prospect",
    )


def _churned(user_id="CHURNED") -> CustomerFeatures:
    return CustomerFeatures(
        user_id=user_id,
        r_score=1,
        f_score=2,
        m_score=1,
        recency_days=200,
        order_count=3,
        total_spend=1500.0,
        return_count=1,
        cart_add_count=0,
        wishlist_count=0,
        days_since_last_seen=200,
        segment="lost",
    )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_sigmoid_zero(self):
        assert abs(_sigmoid(0.0) - 0.5) < 1e-9

    def test_sigmoid_large_positive(self):
        assert _sigmoid(100) > 0.999

    def test_sigmoid_large_negative(self):
        assert _sigmoid(-100) < 0.001

    def test_label_from_score_low(self):
        assert _label_from_score(0.2) == "low"

    def test_label_from_score_medium(self):
        assert _label_from_score(0.5) == "medium"

    def test_label_from_score_high(self):
        assert _label_from_score(0.8) == "high"


# ---------------------------------------------------------------------------
# Purchase Probability Model
# ---------------------------------------------------------------------------

class TestPurchaseProbabilityModel:
    def setup_method(self):
        self.model = PurchaseProbabilityModel()

    def test_champion_buyer_high_probability(self):
        features = _buyer(r_score=5, f_score=5, m_score=5, recency_days=3, cart_add_count=20)
        pred = self.model.score(features)
        assert pred.score >= 0.65, f"Expected high score, got {pred.score}"
        assert pred.label == "high"

    def test_lost_customer_low_probability(self):
        pred = self.model.score(_churned())
        assert pred.score < 0.5, f"Expected low score, got {pred.score}"

    def test_prospect_nonzero_score(self):
        pred = self.model.score(_prospect())
        assert 0.0 < pred.score < 0.8

    def test_score_in_range(self):
        for r in (1, 3, 5):
            for f in (1, 3, 5):
                features = _buyer(r_score=r, f_score=f)
                pred = self.model.score(features)
                assert 0.0 <= pred.score <= 1.0

    def test_high_returns_reduce_score(self):
        normal = self.model.score(_buyer(return_count=0, order_count=10))
        high_return = self.model.score(_buyer(return_count=8, order_count=10))
        assert high_return.score < normal.score

    def test_explanation_not_empty(self):
        pred = self.model.score(_buyer())
        assert len(pred.explanation) > 0

    def test_features_used_populated(self):
        pred = self.model.score(_buyer())
        assert len(pred.features_used) > 0


# ---------------------------------------------------------------------------
# Churn Risk Model
# ---------------------------------------------------------------------------

class TestChurnRiskModel:
    def setup_method(self):
        self.model = ChurnRiskModel()

    def test_churned_customer_high_risk(self):
        pred = self.model.score(_churned())
        assert pred.score >= 0.5, f"Expected high churn risk, got {pred.score}"

    def test_recent_champion_low_risk(self):
        features = _buyer(r_score=5, recency_days=5, cart_add_count=15, wishlist_count=5, segment="champions")
        pred = self.model.score(features)
        assert pred.score < 0.5, f"Expected low churn risk, got {pred.score}"

    def test_prospect_no_orders(self):
        pred = self.model.score(_prospect())
        assert 0.0 <= pred.score <= 1.0

    def test_score_in_range(self):
        for recency in (5, 30, 90, 200):
            features = _buyer(recency_days=recency, order_count=3, r_score=max(1, 5 - recency // 50))
            pred = self.model.score(features)
            assert 0.0 <= pred.score <= 1.0

    def test_churn_increases_with_recency(self):
        fresh = self.model.score(_buyer(recency_days=5, r_score=5))
        stale = self.model.score(_buyer(recency_days=150, r_score=1))
        assert stale.score > fresh.score

    def test_label_consistency(self):
        pred = self.model.score(_buyer())
        if pred.score >= 0.65:
            assert pred.label == "high"
        elif pred.score >= 0.35:
            assert pred.label == "medium"
        else:
            assert pred.label == "low"


# ---------------------------------------------------------------------------
# Offer Response Model
# ---------------------------------------------------------------------------

class TestOfferResponseModel:
    def setup_method(self):
        self.model = OfferResponseModel()

    def test_lost_customer_prefers_win_back(self):
        pred = self.model.score(_churned())
        assert pred.recommended_offer_type == "win_back"

    def test_champion_prefers_loyalty_or_none(self):
        features = _buyer(r_score=5, f_score=5, m_score=5, segment="champions")
        pred = self.model.score(features)
        assert pred.recommended_offer_type in ("loyalty_reward", "none")

    def test_prospect_prefers_discount(self):
        pred = self.model.score(_prospect())
        assert pred.recommended_offer_type == "discount"

    def test_scores_sum_logic(self):
        """All offer type scores are in [0, 1] and the best is selected correctly."""
        pred = self.model.score(_buyer())
        for v in pred.scores.values():
            assert 0.0 <= v <= 1.0
        best = max(pred.scores, key=lambda k: pred.scores[k])
        assert best == pred.recommended_offer_type

    def test_explanation_not_empty(self):
        pred = self.model.score(_buyer())
        assert len(pred.explanation) > 0


# ---------------------------------------------------------------------------
# Model Registry
# ---------------------------------------------------------------------------

class TestModelRegistry:
    def test_score_customers_returns_three_lists(self):
        registry = ModelRegistry()
        customers = [_buyer(user_id=f"U{i}") for i in range(10)]
        purchase, churn, offer = registry.score_customers(customers)
        assert len(purchase) == 10
        assert len(churn) == 10
        assert len(offer) == 10

    def test_registry_populated_after_scoring(self):
        registry = ModelRegistry()
        customers = [_buyer(user_id=f"U{i}") for i in range(5)]
        registry.score_customers(customers)
        models = registry.all()
        assert len(models) == 3
        names = {m.name for m in models}
        assert "purchase_probability" in names
        assert "churn_risk" in names
        assert "offer_response" in names

    def test_model_info_fields(self):
        registry = ModelRegistry()
        customers = [_buyer(user_id=f"U{i}") for i in range(5)]
        registry.score_customers(customers)
        info = registry.get("churn_risk")
        assert info is not None
        assert info.customer_count == 5
        assert 0.0 <= info.avg_score <= 1.0
        assert 0.5 <= info.estimated_auc <= 1.0

    def test_get_registry_singleton(self):
        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_empty_registry(self):
        registry = ModelRegistry()
        assert registry.all() == []
        assert registry.get("purchase_probability") is None
