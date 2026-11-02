"""Pure unit tests of the A/B testing engine (no database)."""
import pytest

from app.experiments.engine import (
    VariantData,
    analyze,
    assign,
    bucket,
    sample_size_per_variant,
    two_proportion_test,
    welch_test,
)

VARIANTS = [{"key": "control", "weight": 1}, {"key": "b", "weight": 1}]


# ------------------------------------------------------------------ assignment
def test_bucket_is_deterministic_and_in_range():
    values = [bucket("exp", f"user{i}") for i in range(2000)]
    assert all(0 <= v < 1 for v in values)
    assert bucket("exp", "u1") == bucket("exp", "u1")
    assert bucket("exp", "u1") != bucket("other", "u1")           # experiments are independent
    assert abs(sum(values) / len(values) - 0.5) < 0.03            # roughly uniform


def test_assignment_respects_traffic_and_weights():
    users = [f"user{i}" for i in range(10000)]
    result = [assign("exp", 50, VARIANTS, u) for u in users]
    inside = [r for r in result if r is not None]
    assert 0.47 < len(inside) / len(users) < 0.53
    assert 0.47 < inside.count("control") / len(inside) < 0.53

    skewed = [assign("exp", 100, [{"key": "a", "weight": 3}, {"key": "b", "weight": 1}], u) for u in users]
    assert 0.72 < skewed.count("a") / len(users) < 0.78
    assert all(assign("exp", 0, VARIANTS, u) is None for u in users[:200])
    assert all(assign("exp", 100, VARIANTS, u) is not None for u in users[:200])
    assert assign("exp", 100, [], "u") is None


def test_assignment_is_sticky_and_raising_traffic_only_adds_customers():
    users = [f"user{i}" for i in range(3000)]
    at_30 = {u: assign("exp", 30, VARIANTS, u) for u in users}
    at_60 = {u: assign("exp", 60, VARIANTS, u) for u in users}
    assert at_30 == {u: assign("exp", 30, VARIANTS, u) for u in users}      # same answer every time
    for u in users:
        if at_30[u] is not None:
            assert at_60[u] == at_30[u]                                    # nobody moves between variants
    assert sum(v is not None for v in at_60.values()) > sum(v is not None for v in at_30.values())


# ------------------------------------------------------------------ statistics
def test_two_proportion_test_detects_a_real_difference():
    r = two_proportion_test(100, 1000, 150, 1000)
    assert r["significant"] is True and r["p_value"] < 0.001
    assert r["diff"] == pytest.approx(0.05) and r["lift"] == pytest.approx(0.5)
    assert r["ci_low"] > 0 and r["ci_high"] > r["ci_low"]


def test_two_proportion_test_no_difference_and_edge_cases():
    same = two_proportion_test(50, 500, 50, 500)
    assert same["p_value"] == pytest.approx(1.0) and same["significant"] is False and same["diff"] == 0
    small = two_proportion_test(5, 50, 6, 50)
    assert small["significant"] is False and small["ci_low"] < 0 < small["ci_high"]
    assert two_proportion_test(0, 0, 1, 10) is None and two_proportion_test(1, 10, 0, 0) is None
    zero_base = two_proportion_test(0, 100, 10, 100)
    assert zero_base["lift"] is None and zero_base["significant"] is True
    assert two_proportion_test(0, 100, 0, 100)["p_value"] == pytest.approx(1.0)       # no variance at all


def test_welch_test():
    control = [0.0] * 90 + [100.0] * 10
    variant = [0.0] * 70 + [100.0] * 30
    r = welch_test(control, variant)
    assert r["control"] == pytest.approx(10) and r["variant"] == pytest.approx(30)
    assert r["significant"] is True and r["lift"] == pytest.approx(2.0)
    same = welch_test(control, list(control))
    assert same["p_value"] == pytest.approx(1.0) and same["significant"] is False
    assert welch_test([1.0], [1.0, 2.0]) is None
    assert welch_test([5.0, 5.0, 5.0], [5.0, 5.0, 5.0])["p_value"] == pytest.approx(1.0)  # zero variance is safe


def test_sample_size_per_variant():
    n = sample_size_per_variant(0.10, 0.10)
    assert 14000 < n < 15500                                    # classic textbook figure (~14.7k)
    assert sample_size_per_variant(0.10, 0.50) < n              # bigger lifts need fewer customers
    assert sample_size_per_variant(0.0) is None and sample_size_per_variant(1.0) is None
    assert sample_size_per_variant(0.1, 0) is None


# --------------------------------------------------------------------- analyze
def vd(key, n, converted, clickers=0, revenue=None, name=None):
    return VariantData(key=key, name=name or key.title(), customers=n, converted=converted, clickers=clickers,
                       revenue=revenue if revenue is not None else [0.0] * n)


def test_analyze_needs_two_variants():
    with pytest.raises(ValueError):
        analyze([vd("control", 10, 1)], "conversion")


def test_verdict_collecting_with_too_little_data():
    out = analyze([vd("control", 10, 1), vd("b", 12, 5)], "conversion")
    assert out["verdict"]["status"] == "collecting" and "10" in out["verdict"]["message"]
    assert out["variants"][0]["comparisons"] is None and out["variants"][1]["comparisons"] is not None
    assert out["sample"]["smallest_variant"] == 10


def test_verdict_winner_control_better_and_inconclusive():
    winner = analyze([vd("control", 400, 40), vd("b", 400, 90, name="Variant B")], "conversion")
    assert winner["verdict"]["status"] == "winner" and winner["verdict"]["winner_key"] == "b"
    assert "Variant B" in winner["verdict"]["message"] and winner["variants"][1]["comparisons"]["conversion"]["significant"]

    loser = analyze([vd("control", 400, 90), vd("b", 400, 40)], "conversion")
    assert loser["verdict"]["status"] == "control_better" and loser["verdict"]["winner_key"] == "control"

    flat = analyze([vd("control", 200, 20), vd("b", 200, 22)], "conversion")
    assert flat["verdict"]["status"] == "inconclusive" and flat["verdict"]["winner_key"] is None
    assert flat["sample"]["needed_per_variant_for_10pct_lift"] > 200


def test_verdict_uses_the_primary_metric():
    same_conversion_more_clicks = [vd("control", 300, 30, clickers=30), vd("b", 300, 30, clickers=120)]
    assert analyze(same_conversion_more_clicks, "conversion")["verdict"]["status"] == "inconclusive"
    assert analyze(same_conversion_more_clicks, "click")["verdict"]["winner_key"] == "b"

    control_rev = [0.0] * 270 + [100.0] * 30
    variant_rev = [0.0] * 210 + [100.0] * 90
    by_revenue = analyze([vd("control", 300, 30, revenue=control_rev), vd("b", 300, 90, revenue=variant_rev)], "revenue")
    assert by_revenue["verdict"]["winner_key"] == "b"
    assert by_revenue["variants"][1]["revenue_per_customer"] == 30.0 and by_revenue["variants"][0]["revenue_per_customer"] == 10.0


def test_best_variant_wins_among_several():
    out = analyze([vd("control", 400, 40), vd("b", 400, 80), vd("c", 400, 110)], "conversion")
    assert out["verdict"]["winner_key"] == "c"


def test_analyze_handles_empty_variants():
    out = analyze([vd("control", 0, 0), vd("b", 0, 0)], "conversion")
    assert out["verdict"]["status"] == "collecting"
    assert out["variants"][0]["conversion_rate"] is None and out["variants"][0]["revenue_per_customer"] is None
