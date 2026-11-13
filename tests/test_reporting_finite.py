import numpy as np
import pandas as pd
import pytest

from pyfpa.io.reporting import forecast_to_excel, to_briefing_md


def _frame():
    return pd.DataFrame({
        "revenue": [100.5, 200.25, 300.25],
        "ebitda": [50.5, -100.25, 250.75],
        "net_income": [20.25, -150.5, 70.25],
        "ending_cash": [1000.0, 900.0, 1000.0],
    }, index=pd.period_range("2026-07", periods=3, freq="M"))


@pytest.mark.parametrize("column", ["revenue", "ebitda", "net_income", "ending_cash"])
@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_briefing_refuses_nonfinite_financial_values(column, invalid):
    frame = _frame()
    frame.loc[frame.index[0], column] = invalid
    with pytest.raises(ValueError, match="finite"):
        to_briefing_md(frame)


@pytest.mark.parametrize("column", ["revenue", "ebitda", "net_income"])
@pytest.mark.parametrize("value", [1e308, -1e308])
def test_briefing_refuses_overflowed_financial_headlines(column, value):
    frame = _frame()
    frame[column] = value
    with pytest.raises(ValueError, match="finite|range"):
        to_briefing_md(frame)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_briefing_refuses_nonfinite_runway_cash(invalid):
    with pytest.raises(ValueError, match="finite"):
        to_briefing_md(_frame(), runway={"min_cash": invalid, "min_week": 1, "first_negative_week": None})


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("existing", [False, True])
def test_invalid_forecast_export_preserves_destination_before_creating_staging(tmp_path, invalid, existing):
    frame = _frame()
    frame["capex"] = [0.0, invalid, 0.0]
    destination = tmp_path / "report.xlsx"
    if existing:
        destination.write_bytes(b"previous valid report")
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError, match="finite"):
        forecast_to_excel(frame, destination)
    assert set(tmp_path.iterdir()) == before
    if existing:
        assert destination.read_bytes() == b"previous valid report"


@pytest.mark.parametrize("column,title", [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("net_income", "Net income")])
def test_integer_headlines_do_not_wrap_at_the_int64_boundary(column, title):
    frame = pd.DataFrame({name: [0, 0, 0, 0] for name in ["revenue", "ebitda", "net_income", "ending_cash"]})
    frame[column] = pd.Series([1 << 62] * 4, dtype="int64")
    expected = f"- **{title}:** $18,446,744,073,709,551,616"
    assert expected in to_briefing_md(frame)


def test_finite_reporting_preserves_headline_and_monthly_values(tmp_path):
    frame = _frame()
    text = to_briefing_md(frame)
    for expected in ["- **Revenue:** $601", "- **EBITDA:** $201", "- **Net income:** -$60", "- **Ending cash:** $1,000", "| 2026-08 | $200 | -$100 | -$150 | $900 |"]:
        assert expected in text
    destination = tmp_path / "report.xlsx"
    forecast_to_excel(frame, destination)
    restored = pd.read_excel(destination, sheet_name="Forecast", index_col=0)
    pd.testing.assert_frame_equal(restored.reset_index(drop=True), frame.reset_index(drop=True), check_dtype=False)


@pytest.mark.parametrize("invalid", [None, pd.NA, "missing"])
def test_briefing_refuses_missing_or_text_financial_values(invalid):
    frame = _frame().astype(object)
    frame.loc[frame.index[0], "revenue"] = invalid
    with pytest.raises(ValueError, match="finite"):
        to_briefing_md(frame)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf"), pd.NA])
def test_forecast_export_refuses_invalid_numbers_in_mixed_columns(tmp_path, invalid):
    frame = _frame()
    frame["notes"] = pd.Series(["review", invalid, "agreed"], index=frame.index, dtype=object)
    with pytest.raises(ValueError, match="finite"):
        forecast_to_excel(frame, tmp_path / "report.xlsx")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("column,title", [("revenue", "Revenue"), ("ebitda", "EBITDA"), ("net_income", "Net income")])
def test_integer_headlines_and_monthly_rows_keep_dollars_with_float_columns(column, title):
    frame = pd.DataFrame({name: [0.25] * 4 for name in ["revenue", "ebitda", "net_income", "ending_cash"]})
    frame[column] = pd.Series([(1 << 62) + 3] * 4, dtype="int64")
    text = to_briefing_md(frame)
    assert f"- **{title}:** $18,446,744,073,709,551,628" in text
    assert text.count("$4,611,686,018,427,387,907") == 4


def test_forecast_export_preserves_text_labels(tmp_path):
    frame = _frame()
    frame["scenario"] = ["base", "delayed", "recovered"]
    destination = tmp_path / "report.xlsx"
    forecast_to_excel(frame, destination)
    restored = pd.read_excel(destination, sheet_name="Forecast", index_col=0)
    assert restored["scenario"].tolist() == frame["scenario"].tolist()


@pytest.mark.parametrize("dtype", ["int64", "Int64", object])
def test_boxed_integer_headline_totals_do_not_wrap(dtype):
    frame = pd.DataFrame({name: [0] * 4 for name in ["revenue", "ebitda", "net_income", "ending_cash"]})
    frame["revenue"] = pd.Series([np.int64(1 << 62)] * 4, dtype=dtype)
    assert "- **Revenue:** $18,446,744,073,709,551,616" in to_briefing_md(frame)


@pytest.mark.parametrize("dtype", ["int64", "Int64", object])
def test_minimum_signed_integer_cash_keeps_its_sign(dtype):
    frame = _frame()
    frame["ending_cash"] = pd.Series([np.int64(-(1 << 63))] * len(frame), index=frame.index, dtype=dtype)
    text = to_briefing_md(frame)
    assert "- **Ending cash:** -$9,223,372,036,854,775,808" in text
    assert text.count("-$9,223,372,036,854,775,808") == 4
    assert "-$-" not in text


def test_minimum_signed_integer_runway_cash_keeps_its_sign():
    runway = {"min_cash": np.int64(-(1 << 63)), "min_week": 1, "first_negative_week": 1}
    text = to_briefing_md(_frame(), runway=runway)
    assert "- **Trough:** -$9,223,372,036,854,775,808 (week 1)" in text
