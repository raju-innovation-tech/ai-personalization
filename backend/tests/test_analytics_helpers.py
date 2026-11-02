from app.analytics.report import change, funnel_rows, kpi


def test_change_and_kpi():
    assert change(150, 100) == 0.5
    assert change(50, 100) == -0.5
    assert change(10, 0) is None and change(10, None) is None
    assert kpi(12.345, 10) == {"value": 12.35, "previous": 10, "change": 0.2345}
    assert kpi(5, None) == {"value": 5, "previous": None, "change": None}


def test_funnel_rows_rates():
    rows = funnel_rows([100, 40, 20, 10])
    assert [r["customers"] for r in rows] == [100, 40, 20, 10]
    assert rows[1]["rate_from_start"] == 0.4 and rows[1]["rate_from_previous"] == 0.4
    assert rows[3]["rate_from_start"] == 0.1 and rows[3]["rate_from_previous"] == 0.5
    empty = funnel_rows([0, 0, 0, 0])
    assert empty[0]["rate_from_start"] is None and empty[1]["rate_from_previous"] is None
