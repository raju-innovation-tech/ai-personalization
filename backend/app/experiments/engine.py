"""
A/B testing engine (Phase 6) - pure Python (standard library only).

* bucket / assign : deterministic, sticky customer -> variant assignment (no state needed)
* two_proportion_test, welch_test : significance of a difference vs control
* sample_size_per_variant         : how many customers a test needs to detect a given lift
* analyze                         : per-variant metrics, comparisons and a plain-language verdict
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from statistics import NormalDist

KINDS = ("recommendations", "offers")
METRICS = ("conversion", "click", "revenue")
STATUSES = ("draft", "running", "paused", "completed")
RECOMMENDATION_STRATEGIES = ("hybrid", "content", "collaborative", "popular")

ALPHA = 0.05
MIN_SAMPLE_PER_VARIANT = 30
_NORMAL = NormalDist()
_Z_CRIT = _NORMAL.inv_cdf(1 - ALPHA / 2)  # 1.96


# ----------------------------------------------------------------- assignment
def bucket(experiment_key: str, user_id: str) -> float:
    """A stable number in [0, 1) for this customer in this experiment (different experiments are independent)."""
    digest = hashlib.sha256(f"{experiment_key}:{user_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def assign(experiment_key: str, traffic_percent: int, variants: list[dict], user_id: str) -> str | None:
    """
    Variant key for this customer, or None when the customer is outside the experiment's traffic share.

    Two independent hashes are used (one decides *whether* the customer takes part, the other *which* variant),
    so the answer is stable and raising traffic_percent only adds customers without moving anyone between variants.
    """
    if not variants:
        return None
    share = max(0, min(traffic_percent, 100)) / 100.0
    if share <= 0 or bucket(f"{experiment_key}#traffic", user_id) >= share:
        return None
    position = bucket(f"{experiment_key}#variant", user_id)
    total = sum(float(v.get("weight", 1)) for v in variants)
    if total <= 0:
        return variants[0]["key"]
    cumulative = 0.0
    for variant in variants:
        cumulative += float(variant.get("weight", 1)) / total
        if position < cumulative:
            return variant["key"]
    return variants[-1]["key"]  # float rounding safety net


# ----------------------------------------------------------------- statistics
def two_proportion_test(x_control: int, n_control: int, x_variant: int, n_variant: int) -> dict | None:
    """Two-sided z-test for a difference in rates (variant minus control)."""
    if n_control <= 0 or n_variant <= 0:
        return None
    p1, p2 = x_control / n_control, x_variant / n_variant
    pooled = (x_control + x_variant) / (n_control + n_variant)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / n_control + 1 / n_variant))
    z = (p2 - p1) / se_pooled if se_pooled > 0 else 0.0
    p_value = 2 * (1 - _NORMAL.cdf(abs(z)))
    se_diff = math.sqrt(p1 * (1 - p1) / n_control + p2 * (1 - p2) / n_variant)
    diff = p2 - p1
    return {
        "control": p1,
        "variant": p2,
        "diff": diff,
        "lift": (diff / p1) if p1 > 0 else None,
        "p_value": p_value,
        "ci_low": diff - _Z_CRIT * se_diff,
        "ci_high": diff + _Z_CRIT * se_diff,
        "significant": p_value < ALPHA,
    }


def welch_test(control: list[float], variant: list[float]) -> dict | None:
    """Welch's t-test for a difference in means (normal approximation of the p-value; fine for n >= 30)."""
    n1, n2 = len(control), len(variant)
    if n1 < 2 or n2 < 2:
        return None
    m1, m2 = sum(control) / n1, sum(variant) / n2
    v1 = sum((x - m1) ** 2 for x in control) / (n1 - 1)
    v2 = sum((x - m2) ** 2 for x in variant) / (n2 - 1)
    se = math.sqrt(v1 / n1 + v2 / n2)
    diff = m2 - m1
    t = diff / se if se > 0 else 0.0
    p_value = 2 * (1 - _NORMAL.cdf(abs(t)))
    return {
        "control": m1,
        "variant": m2,
        "diff": diff,
        "lift": (diff / m1) if m1 > 0 else None,
        "p_value": p_value,
        "ci_low": diff - _Z_CRIT * se,
        "ci_high": diff + _Z_CRIT * se,
        "significant": p_value < ALPHA,
    }


def sample_size_per_variant(baseline_rate: float, relative_lift: float = 0.10, power: float = 0.80) -> int | None:
    """Customers needed per variant to detect `relative_lift` over `baseline_rate` (two-sided, alpha 0.05)."""
    if baseline_rate <= 0 or baseline_rate >= 1 or relative_lift <= 0:
        return None
    p1 = baseline_rate
    p2 = min(baseline_rate * (1 + relative_lift), 0.999)
    pbar = (p1 + p2) / 2
    z_beta = _NORMAL.inv_cdf(power)
    numerator = (_Z_CRIT * math.sqrt(2 * pbar * (1 - pbar)) + z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return int(math.ceil(numerator / (p2 - p1) ** 2))


# -------------------------------------------------------------------- analysis
@dataclass
class VariantData:
    key: str
    name: str
    customers: int = 0  # exposed customers
    converted: int = 0  # bought something after exposure
    clickers: int = 0  # clicked a recommendation / offer after exposure
    revenue: list[float] = field(default_factory=list)  # per exposed customer (zeros included)


_METRIC_LABELS = {"conversion": "purchase conversion", "click": "click rate", "revenue": "revenue per customer"}


def _rates(v: VariantData) -> dict:
    n = v.customers
    return {
        "customers": n,
        "conversions": v.converted,
        "conversion_rate": round(v.converted / n, 4) if n else None,
        "clickers": v.clickers,
        "click_rate": round(v.clickers / n, 4) if n else None,
        "revenue_total": round(sum(v.revenue), 2),
        "revenue_per_customer": round(sum(v.revenue) / n, 2) if n else None,
    }


def _round_comparison(c: dict | None) -> dict | None:
    if c is None:
        return None
    return {k: (round(val, 4) if isinstance(val, float) else val) for k, val in c.items()}


def analyze(variants: list[VariantData], primary_metric: str, min_sample: int = MIN_SAMPLE_PER_VARIANT) -> dict:
    """The first variant is the control. Returns per-variant numbers, comparisons vs control and a verdict."""
    if len(variants) < 2:
        raise ValueError("an experiment needs at least two variants")
    control = variants[0]
    rows: list[dict] = []
    for index, v in enumerate(variants):
        row = {"key": v.key, "name": v.name, "is_control": index == 0, **_rates(v), "comparisons": None}
        if index > 0:
            row["comparisons"] = {
                "conversion": _round_comparison(two_proportion_test(control.converted, control.customers, v.converted, v.customers)),
                "click": _round_comparison(two_proportion_test(control.clickers, control.customers, v.clickers, v.customers)),
                "revenue": _round_comparison(welch_test(control.revenue, v.revenue)),
            }
        rows.append(row)

    smallest = min(v.customers for v in variants)
    baseline = (control.converted / control.customers) if control.customers else 0.0
    needed = sample_size_per_variant(baseline)
    sample = {
        "min_per_variant": min_sample,
        "smallest_variant": smallest,
        "needed_per_variant_for_10pct_lift": needed,
    }

    label = _METRIC_LABELS[primary_metric]
    verdict: dict
    if smallest < min_sample:
        verdict = {
            "status": "collecting",
            "winner_key": None,
            "message": f"Collecting data: every variant needs at least {min_sample} exposed customers (the smallest has {smallest}).",
        }
    else:
        better, worse = [], []
        for row in rows[1:]:
            comparison = row["comparisons"][primary_metric]
            if comparison and comparison["significant"]:
                (better if comparison["diff"] > 0 else worse).append((row, comparison))
        if better:
            best_row, best = max(better, key=lambda item: item[1]["variant"])
            lift = best["lift"]
            lift_text = f"{lift:+.1%} " if lift is not None else ""
            verdict = {
                "status": "winner",
                "winner_key": best_row["key"],
                "message": f"{best_row['name']} beats the control on {label} ({lift_text}p = {best['p_value']:.3f}).",
            }
        elif worse:
            verdict = {
                "status": "control_better",
                "winner_key": control.key,
                "message": f"The control is significantly better than {', '.join(r['name'] for r, _ in worse)} on {label}.",
            }
        else:
            hint = f" About {needed:,} customers per variant are needed to detect a 10% lift." if needed else ""
            verdict = {
                "status": "inconclusive",
                "winner_key": None,
                "message": f"No significant difference on {label} yet.{hint}",
            }
    return {"primary_metric": primary_metric, "variants": rows, "verdict": verdict, "sample": sample}
