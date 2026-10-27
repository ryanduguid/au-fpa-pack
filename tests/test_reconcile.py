import pytest

from pyfpa.analysis.reconcile import reconcile


def test_reconcile_flags_within_tolerance():
    model = {"revenue": 1000.0, "net_income": 100.0}
    actual = {"revenue": 1005.0, "net_income": 130.0}
    df = reconcile(model, actual, tolerance=0.01)
    rev = df.loc["revenue"]
    assert rev["variance"] == pytest.approx(-5.0)
    assert rev["variance_pct"] == pytest.approx(-5.0 / 1005.0)
    assert bool(rev["within_tolerance"]) is True
    ni = df.loc["net_income"]
    assert bool(ni["within_tolerance"]) is False


def test_reconcile_zero_actual():
    df = reconcile({"x": 0.0}, {"x": 0.0}, tolerance=0.01)
    assert bool(df.loc["x"]["within_tolerance"]) is True


def test_reconcile_missing_model_line_is_refused():
    with pytest.raises(ValueError, match="line sets differ"):
        reconcile({}, {"revenue": 100.0}, tolerance=0.01)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 10**1000],
                         ids=["nan", "positive_inf", "negative_inf", "unrepresentable_int"])
@pytest.mark.parametrize("side", ["model", "actual"])
def test_reconcile_refuses_unsupported_operands(value, side):
    model, actual = {"cash": 100.0}, {"cash": 100.0}
    (model if side == "model" else actual)["cash"] = value
    with pytest.raises(ValueError, match="cash.*finite"):
        reconcile(model, actual)


@pytest.mark.parametrize("model,actual,term", [
    (1e308, -1e308, "variance"),
    (-1e308, 1e308, "variance"),
    (1e308, 1e-308, "percentage"),
])
def test_reconcile_refuses_unsupported_derived_results(model, actual, term):
    with pytest.raises(ValueError, match=f"cash.*{term}.*finite"):
        reconcile({"cash": model}, {"cash": actual}, tolerance=float("inf"))


@pytest.mark.parametrize("model,actual,expected", [
    (110.0, 100.0, 0.1),
    (90.0, 100.0, -0.1),
    (2.9999999999999996, 3.0, -1.4802973661668753e-16),
    (3.0000000000000004, 3.0, 1.4802973661668753e-16),
    (1e308, 1e308, 0.0),
])
def test_reconcile_preserves_supported_rounding(model, actual, expected):
    result = reconcile({"cash": model}, {"cash": actual}, tolerance=float("inf"))
    assert result.loc["cash", "variance_pct"] == expected
    assert bool(result.loc["cash", "within_tolerance"])
