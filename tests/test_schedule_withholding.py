# Copyright 2026 Ryan Duguid
# SPDX-License-Identifier: LicenseRef-Duguid-Public-Attribution-1.0

"""Fabricated role pays; native results follow the shared JSON boundary."""

import json
import subprocess
import sys
from dataclasses import replace
from datetime import date, datetime
from decimal import Context, Decimal, localcontext
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from pyfpa.au.payg_withholding import RolePay, RoleWithholding
from pyfpa.au.payroll_settlement import settlement_events
from pyfpa.io.native_tax import calculate_role_withholding

DAY = date(2026, 7, 3)
PAY = RolePay("Role A", DAY, Decimal("370.00"), "weekly", 2, True)


def _response(payment=PAY, **changes):
    body = {
        "ok": True, "engine": "australian-tax-calculators", "engine_version": "1.0.0",
        "calculation": "payg_withholding", "period": f"{payment.year} {payment.pay_period}",
        "amounts": {"withholding": "1.00"}, "rates": {"scale": str(payment.scale)},
        "scope": "regular earnings only",
        "sources": ["https://www.ato.gov.au/"], "source_checked": "2026-07-01",
        "warnings": ["Operator-confirmed scope; obtain human review."],
    }
    body.update(changes)
    return body


def _run(tmp_path, body=None, *, code=0, stdout=None, payments=(PAY,), **kwargs):
    executable = tmp_path / "calculator.exe"
    executable.touch()
    process = subprocess.CompletedProcess([], code, stdout if stdout is not None else json.dumps(
        _response() if body is None else body,
    ), "")
    with patch("pyfpa.io.native_tax.subprocess.run", return_value=process) as run:
        results = calculate_role_withholding(
            payments, executable=executable, engine_version="1.0.0", **kwargs,
        )
    return results, run


def _frame(gross=370.0, bonus=0.0):
    return pd.DataFrame({
        "gross_wages": [gross], "bonuses": [bonus], "super_guarantee": [44.4],
        "payroll_tax": [0.0], "workers_comp": [0.0],
    }, index=pd.period_range("2026-07", periods=1, freq="M"))


def _settle(results, *, gross=370.0, bonus=0.0, paydays=(DAY,), rules=None, **kwargs):
    return settlement_events(
        _frame(gross, bonus), paydays, role_withholding=results,
        due_rules={"payg_withholding": lambda day: day, "super_guarantee": lambda day: day}
        if rules is None else rules, **kwargs,
    )


def test_native_boundary_preserves_evidence_and_passes_aud_strings_on_stdin(tmp_path):
    results, run = _run(tmp_path)
    assert results[0].withholding == Decimal("1.00")
    assert json.loads(results[0].evidence_json) == _response()
    arguments, options = run.call_args
    assert arguments[0][1:] == ["payg-withholding", "--refusal-json"]
    assert json.loads(options["input"]) == {
        "earnings": "370.00", "pay_period": "weekly", "scale": 2,
        "year": "2026-27", "scope_confirmed": True,
    }
    assert options["shell"] is False
    assert options["timeout"] == 10
    assert "370" not in " ".join(arguments[0])


def test_adapter_uses_a_real_local_process_and_stdin(tmp_path, monkeypatch):
    # A synthetic protocol peer, not a tax oracle or a claim about a native release.
    peer = tmp_path / "payg-withholding"
    peer.write_text(
        "import json, sys\nfacts = json.load(sys.stdin)\n"
        "assert facts['earnings'] == '370.00' and facts['year'] == '2026-27'\n"
        f"print({json.dumps(_response())!r})\n", encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    results = calculate_role_withholding([PAY], executable=Path(sys.executable), engine_version="1.0.0")
    assert results[0].withholding == Decimal("1.00")


def test_schedule_results_drive_net_pay_without_changing_other_costs(tmp_path):
    results, _ = _run(tmp_path)
    events = _settle(results)
    assert {event.component: event.amount for event in events} == {
        "net_wages": 369.0, "payg_withholding": 1.0, "super_guarantee": 44.4,
    }


def test_roles_keep_individual_scales_and_unequal_paydays(tmp_path):
    second_day = date(2026, 7, 10)
    payments = [PAY, replace(PAY, role_name="Role B", payday=second_day, scale=1, earnings=Decimal("630"))]
    executable = tmp_path / "calculator.exe"
    executable.touch()
    responses = [subprocess.CompletedProcess([], 0, json.dumps(_response(payment)), "") for payment in payments]
    with patch("pyfpa.io.native_tax.subprocess.run", side_effect=responses) as run:
        results = calculate_role_withholding(payments, executable=executable, engine_version="1.0.0")
    assert [json.loads(call.kwargs["input"])["scale"] for call in run.call_args_list] == [2, 1]
    events = _settle(results, gross=1000, paydays=(DAY, second_day))
    assert [event.amount for event in events if event.component == "net_wages"] == [369, 629]
    assert sum(event.amount for event in events if event.component == "super_guarantee") == 44.4


def test_multiple_roles_on_one_payday_add_their_individual_withholding():
    second = replace(PAY, role_name="Role B", earnings=Decimal("630"), scale=1)
    results = [RoleWithholding(PAY, Decimal(1), "{}"), RoleWithholding(second, Decimal(100), "{}")]
    events = _settle(results, gross=1000)
    assert next(event.amount for event in events if event.component == "net_wages") == 899


@pytest.mark.parametrize(("day", "year"), [(date(2026, 6, 30), "2025-26"), (DAY, "2026-27")])
def test_income_year_follows_each_pay_date(day, year, tmp_path):
    payment = replace(PAY, payday=day)
    _, run = _run(tmp_path, _response(payment), payments=(payment,))
    assert json.loads(run.call_args.kwargs["input"])["year"] == year


@pytest.mark.parametrize("changes", [
    {"role_name": " "}, {"payday": datetime(2026, 7, 3)}, {"earnings": 370.0},
    {"earnings": Decimal("NaN")}, {"earnings": Decimal("Infinity")},
    {"earnings": Decimal("-1")}, {"earnings": Decimal("1.001")},
    {"pay_period": "quarterly"}, {"scale": True}, {"scale": 4},
    {"scope_confirmed": False}, {"scope_confirmed": 1},
])
def test_role_pay_rejects_invalid_or_out_of_scope_inputs(changes):
    with pytest.raises(ValueError):
        replace(PAY, **changes)


@pytest.mark.parametrize(("amount", "evidence"), [(Decimal("371"), "{}"), (Decimal(1), " ")])
def test_withholding_record_rejects_impossible_or_unevidenced_results(amount, evidence):
    with pytest.raises(ValueError):
        RoleWithholding(PAY, amount, evidence)


@pytest.mark.parametrize("changes", [
    {"engine": "other"}, {"engine_version": "0.2.0"}, {"calculation": "annual_tax"},
    {"period": "2025-26 weekly"}, {"warnings": None}, {"warnings": [1]},
    {"warnings": []}, {"warnings": [" "]}, {"sources": []}, {"sources": [{}]},
    {"sources": [" "]}, {"source_checked": None}, {"source_checked": " "},
    {"scope": None}, {"scope": " "},
    {"amounts": []}, {"amounts": {"withholding": 1}},
    {"amounts": {"withholding": "invalid"}}, {"amounts": {"withholding": "NaN"}},
    {"amounts": {"withholding": "-1"}}, {"amounts": {"withholding": "1.001"}},
    {"amounts": {"withholding": "371"}},
    # Schedule 1 withholds whole dollars, and the result must be for the scale sent.
    {"amounts": {"withholding": "1.50"}},
    {"rates": {"scale": "4"}}, {"rates": {}}, {"rates": None},
])
def test_native_boundary_refuses_invalid_results(tmp_path, changes):
    with pytest.raises(ValueError):
        _run(tmp_path, _response(**changes))


@pytest.mark.parametrize("stdout", ["invalid", "[]", '{"ok":true,"ok":false}'])
def test_native_boundary_refuses_malformed_or_duplicate_json(tmp_path, stdout):
    with pytest.raises(ValueError):
        _run(tmp_path, stdout=stdout)


@pytest.mark.parametrize("code", [0, 2])
def test_refusals_never_fall_back_to_an_average_rate(tmp_path, code):
    with pytest.raises(ValueError, match="scope.unconfirmed"):
        _run(tmp_path, {"ok": False, "code": "scope.unconfirmed"}, code=code)


def test_a_refusal_names_the_role_payday_and_the_calculators_message(tmp_path):
    refusal = {"ok": False, "code": "period.unsupported", "message": "2027-28 is not supported"}
    with pytest.raises(ValueError, match=r"Role A on 2026-07-03: period\.unsupported: 2027-28 is not"):
        _run(tmp_path, refusal, code=2)


def test_a_failed_process_without_json_reports_its_exit_code_and_stderr(tmp_path):
    # A build without --refusal-json prints its usage to stderr and nothing to stdout.
    executable = tmp_path / "calculator.exe"
    executable.touch()
    process = subprocess.CompletedProcess([], 2, "", "usage: australian-tax-calculators COMMAND\nmore\n")
    with patch("pyfpa.io.native_tax.subprocess.run", return_value=process), pytest.raises(
        ValueError, match="exited 2: usage: australian-tax-calculators COMMAND$",
    ):
        calculate_role_withholding([PAY], executable=executable, engine_version="1.0.0")


def test_a_wrong_engine_version_names_the_version_returned(tmp_path):
    with pytest.raises(ValueError, match="australian-tax-calculators 0.2.0"):
        _run(tmp_path, _response(engine_version="0.2.0"))


@pytest.mark.parametrize("error", [OSError("unavailable"), subprocess.TimeoutExpired("calculator", 10), UnicodeError()])
def test_native_process_failures_stop_the_projection(tmp_path, error):
    executable = tmp_path / "calculator.exe"
    executable.touch()
    with patch("pyfpa.io.native_tax.subprocess.run", side_effect=error), pytest.raises(ValueError, match="could not complete"):
        calculate_role_withholding([PAY], executable=executable, engine_version="1.0.0")


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True])
def test_native_timeout_must_be_explicitly_bounded(tmp_path, timeout):
    with pytest.raises(ValueError, match="timeout"):
        _run(tmp_path, timeout=timeout)


def test_native_adapter_needs_an_existing_absolute_file_and_a_version(tmp_path):
    with pytest.raises(ValueError, match="absolute"):
        calculate_role_withholding([PAY], executable=tmp_path / "missing", engine_version="1.0.0")
    executable = tmp_path / "calculator.exe"
    executable.touch()
    with pytest.raises(ValueError, match="version"):
        calculate_role_withholding([PAY], executable=executable, engine_version=" ")
    assert calculate_role_withholding([], executable=executable, engine_version="1.0.0") == []


@pytest.mark.parametrize(("kwargs", "message"), [
    ({"gross": 371}, "reconcile"), ({"gross": 370.01}, "reconcile"), ({"gross": float("nan")}, "reconcile"),
    ({"bonus": 1}, "bonuses"), ({"payg_withholding_rate_assumption": 0.2}, "either"),
    ({"paydays": ()}, "undeclared"), ({"rules": {"super_guarantee": lambda day: day}}, "no due rule"),
])
def test_schedule_mode_refuses_ambiguous_or_unreconciled_inputs(kwargs, message):
    with pytest.raises(ValueError, match=message):
        _settle([RoleWithholding(PAY, Decimal(1), "{}")], **kwargs)


def test_cent_rounded_pays_reconcile_to_the_unrounded_monthly_frame():
    # Two roles on 52,000 a year: the frame holds 2 * 52000 / 12 and each pay is whole cents.
    pays = [replace(PAY, role_name=name, pay_period="monthly", earnings=Decimal("4333.33"))
            for name in ("Role A", "Role B")]
    events = _settle([RoleWithholding(pay, Decimal(600), "{}") for pay in pays], gross=2 * 52000 / 12)
    assert next(event.amount for event in events if event.component == "net_wages") == 7466.66


def test_schedule_arithmetic_ignores_a_callers_low_decimal_precision():
    pay = replace(PAY, pay_period="monthly", earnings=Decimal("5000.00"))
    result = RoleWithholding(pay, Decimal(810), "{}")
    with localcontext(Context(prec=2)):
        events = _settle([result], gross=5000)
    assert {event.component: event.amount for event in events if event.component != "super_guarantee"} == {
        "net_wages": 4190.0, "payg_withholding": 810.0,
    }


def test_role_pays_too_large_to_add_exactly_are_refused():
    huge = replace(PAY, earnings=Decimal("1E+30"))
    small = replace(PAY, role_name="Role B", earnings=Decimal("0.01"))
    results = [RoleWithholding(huge, Decimal(0), "{}"), RoleWithholding(small, Decimal(0), "{}")]
    with pytest.raises(ValueError, match="exactly"):
        _settle(results, gross=1e30)


def test_duplicate_roles_and_missing_paydays_are_refused():
    result = RoleWithholding(PAY, Decimal(1), "{}")
    with pytest.raises(ValueError, match="repeats"):
        _settle([result, result], gross=740)
    with pytest.raises(ValueError, match="missing a payday"):
        _settle([result], paydays=(DAY, date(2026, 7, 10)))


def test_zero_schedule_and_zero_withholding_need_no_tax_due_rule():
    zero = RoleWithholding(replace(PAY, earnings=Decimal(0)), Decimal(0), "{}")
    events = _settle([zero], gross=0, rules={"super_guarantee": lambda day: day})
    assert [event.component for event in events] == ["super_guarantee"]
    events = _settle([], gross=0)
    assert [event.component for event in events] == ["super_guarantee"]


def test_average_rate_remains_the_explicit_default_mode():
    events = settlement_events(_frame(), [DAY], payg_withholding_rate_assumption=0.2,
                               due_rules={"payg_withholding": lambda day: day, "super_guarantee": lambda day: day})
    assert next(event.amount for event in events if event.component == "payg_withholding") == 74
    with pytest.raises(ValueError, match="rate_assumption"):
        settlement_events(_frame(), [DAY], due_rules={})
