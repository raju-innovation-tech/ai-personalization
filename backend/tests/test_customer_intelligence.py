"""Pure unit tests: purchase value, RFM scoring, segment rules (no database)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.customers.intelligence import (
    CustomerStats,
    assign_segment,
    build_profiles,
    purchase_quantity,
    purchase_value,
    score_frequency,
    score_quintiles,
)
from app.segments.definitions import SEGMENT_BY_KEY, SEGMENTS

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


# ------------------------------------------------------------- purchase value
@pytest.mark.parametrize(
    "metadata, catalog, expected",
    [
        ({}, 100.0, 100.0),                                   # catalog price x 1
        ({"quantity": 3}, 100.0, 300.0),
        ({"quantity": "2"}, 50.0, 100.0),                     # numeric strings are accepted
        ({"price": 80, "quantity": 2}, 100.0, 160.0),         # event price beats catalog price
        ({"amount": 999.5, "quantity": 5}, 100.0, 999.5),     # amount is the line total
        ({"amount": -5}, 100.0, 100.0),                       # negative amount ignored
        ({"quantity": 0}, 100.0, 100.0),                      # nonsense quantity -> 1
        ({"quantity": "abc", "price": "x"}, 70.0, 70.0),      # junk ignored
        ({"quantity": True}, 10.0, 10.0),                     # booleans are not numbers
        ({"amount": float("nan")}, 10.0, 10.0),
        ({}, None, 0.0),                                      # unknown product, no price
        (None, 25.0, 25.0),                                   # missing metadata
    ],
)
def test_purchase_value(metadata, catalog, expected):
    assert purchase_value(metadata, catalog) == expected


def test_purchase_quantity_is_capped():
    assert purchase_quantity({"quantity": 10**9}) == 1000
    assert purchase_quantity({"quantity": 2.9}) == 2


# -------------------------------------------------------------------- scoring
def test_score_quintiles_spreads_distinct_values_over_1_to_5():
    scores = score_quintiles([float(v) for v in range(1, 11)])
    assert scores == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_score_quintiles_ties_share_a_score_and_bottom_group_is_1():
    scores = score_quintiles([1, 1, 1, 1, 1, 1, 1, 1, 1, 10])
    assert scores[:9] == [1] * 9 and scores[9] == 5


def test_score_quintiles_all_equal_is_neutral_and_empty_is_empty():
    assert score_quintiles([7, 7, 7]) == [3, 3, 3]
    assert score_quintiles([]) == []
    assert score_quintiles([42.0]) == [3]


def test_score_quintiles_is_monotonic():
    values = [5, 1, 9, 3, 3, 7, 2]
    scores = score_quintiles([float(v) for v in values])
    for a in range(len(values)):
        for b in range(len(values)):
            if values[a] < values[b]:
                assert scores[a] <= scores[b]
            if values[a] == values[b]:
                assert scores[a] == scores[b]


@pytest.mark.parametrize("orders, expected", [(0, 1), (1, 1), (2, 2), (3, 3), (4, 4), (5, 4), (6, 5), (40, 5)])
def test_score_frequency_bins(orders, expected):
    assert score_frequency(orders) == expected


# ------------------------------------------------------------------- segments
def seg(orders=3, recency=60, r=3, f=3, m=3, seen=10):
    return assign_segment(orders=orders, recency_days=recency, r=r, f=f, m=m, days_since_seen=seen)


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        (dict(orders=0, recency=None, r=None, f=None, m=None, seen=5), "prospect"),
        (dict(orders=0, recency=None, r=None, f=None, m=None, seen=90), "inactive"),
        (dict(orders=0, recency=None, r=None, f=None, m=None, seen=None), "inactive"),
        (dict(orders=1, recency=10, r=5, f=1, m=5), "new_customer"),
        (dict(orders=1, recency=100, r=2, f=1, m=1), "hibernating"),
        (dict(orders=6, recency=3, r=5, f=5, m=5), "champions"),
        (dict(orders=6, recency=200, r=1, f=5, m=5), "cant_lose"),
        (dict(orders=4, recency=40, r=4, f=4, m=2), "loyal"),
        (dict(orders=4, recency=70, r=3, f=4, m=1), "loyal"),
        (dict(orders=3, recency=150, r=2, f=3, m=3), "at_risk"),
        (dict(orders=3, recency=70, r=3, f=3, m=3), "need_attention"),
        (dict(orders=2, recency=35, r=5, f=2, m=3), "potential_loyalist"),
        (dict(orders=2, recency=80, r=3, f=1, m=2), "about_to_sleep"),
        (dict(orders=2, recency=150, r=2, f=1, m=1), "hibernating"),
        (dict(orders=2, recency=300, r=1, f=1, m=1), "lost"),
    ],
)
def test_segment_rules(kwargs, expected):
    assert seg(**kwargs) == expected


def test_every_rule_outcome_is_a_defined_segment():
    for r in range(1, 6):
        for f in range(1, 6):
            for m in range(1, 6):
                for orders in (1, 2, 7):
                    for recency in (5, 90):
                        assert seg(orders=orders, recency=recency, r=r, f=f, m=m) in SEGMENT_BY_KEY


def test_segment_definitions_are_complete_and_unique():
    keys = [s.key for s in SEGMENTS]
    assert len(keys) == len(set(keys)) == 12
    assert all(s.name and s.description and s.action for s in SEGMENTS)


# ------------------------------------------------------------------- profiles
def test_build_profiles_scores_buyers_and_leaves_non_buyers_unscored():
    stats = [
        CustomerStats("whale", last_seen=NOW, orders=8, spend=90000, last_order=NOW - timedelta(days=2)),
        CustomerStats("mid", last_seen=NOW, orders=3, spend=9000, last_order=NOW - timedelta(days=40)),
        CustomerStats("old", last_seen=NOW - timedelta(days=200), orders=1, spend=500, last_order=NOW - timedelta(days=200)),
        CustomerStats("browser", last_seen=NOW - timedelta(days=2), orders=0),
        CustomerStats("ghost", last_seen=NOW - timedelta(days=120), orders=0),
    ]
    by_id = {p["user_id"]: p for p in build_profiles(stats, now=NOW)}

    assert by_id["whale"]["rfm_code"] == "555"
    assert by_id["whale"]["segment"] == "champions"
    assert by_id["old"]["r_score"] == 1 and by_id["old"]["segment"] == "lost"
    assert by_id["mid"]["f_score"] == 3 and by_id["whale"]["f_score"] == 5 and by_id["old"]["f_score"] == 1
    assert by_id["whale"]["recency_days"] == 2 and by_id["whale"]["avg_order_value"] == 11250.0
    assert by_id["browser"]["segment"] == "prospect" and by_id["browser"]["rfm_code"] is None
    assert by_id["browser"]["avg_order_value"] is None
    assert by_id["ghost"]["segment"] == "inactive"
    assert all(p["profile_computed_at"] == NOW for p in by_id.values())


def test_build_profiles_never_reports_negative_spend_and_handles_naive_datetimes():
    naive = datetime(2026, 10, 1, 12, 0)  # no tzinfo
    stats = [CustomerStats("u", last_seen=naive, orders=1, spend=-50.0, last_order=naive)]
    profile = build_profiles(stats, now=NOW)[0]
    assert profile["total_spend"] == 0.0
    assert profile["recency_days"] == 7


def test_build_profiles_with_no_customers():
    assert build_profiles([], now=NOW) == []
