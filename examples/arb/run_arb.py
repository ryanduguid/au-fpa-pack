"""ARB Corporation worked example - full pipeline.

Phase A reproduces FY2025 operating mechanics from actual drivers.
Phase B replays 2 FY2025 champion/challenger holdout epochs.
Phase C forecasts FY2026-FY2027 from the August 2025 4E view.
Phase D labels a Thai Baht / US-tariff COGS sensitivity.

Run:  python3 examples/arb/run_arb.py --output-dir <dir>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import arb_model as am

from pyfpa.analysis.reconcile import reconcile
from pyfpa.io.reporting import to_briefing_md
from pyfpa.research import save_epoch, save_research_objective

OUT = HERE / "output"
RESEARCH = HERE / ".fpa" / "research"


def phase_a() -> str:
    model = am.phase_a_model("FY2025", "FY2024")
    actual = am.phase_a_actual("FY2025", "FY2024")
    rec = reconcile(model, actual, tolerance=0.01)
    lines = [
        "# Phase A - FY2025 actual-driver reproduction",
        "",
        "The engine is driven with ARB's reported sales mix, materials/sales COGS,",
        "working-capital days, D&A and PPE capex. EBITDA is EBIT + D&A.",
        "Gross profit is sales minus materials (ARB does not print GP).",
        "`operating_cash_flow_before_tax` is a constructed proxy on both sides:",
        "EBITDA plus the balance-sheet working-capital movement, not the reported",
        "cash-flow statement.",
        "",
        "| Line | Model | Actual or proxy | Variance |",
        "|---|--:|--:|--:|",
    ]
    for line, row in rec.iterrows():
        lines.append(
            f"| {line} | {row['model']:,.0f} | {row['actual']:,.0f} | "
            f"{row['variance_pct'] * 100:+.2f}% |"
        )
    lines += [
        "",
        "This validates operating arithmetic, not forecast skill. Target-year",
        "drivers are inputs. Tax, franking, associates, and acquisitions sit",
        "outside the engine.",
        "",
    ]
    return "\n".join(lines)


def phase_b() -> str:
    epochs = am.historical_research_epochs()
    lines = [
        "# Phase B - FY2025 historical holdout research",
        "",
        "The champion is a flat FY2024 run rate. FY2025 is held out.",
        "Working-capital days are not a holdout metric: AR barely moved while",
        "sales grew, and H2 destocking is a management action.",
        "",
        "| Epoch | Hypothesis | Status | Objective gain |",
        "|---|---|---|--:|",
    ]
    for epoch in epochs:
        lines.append(
            f"| {epoch.epoch_id} | {epoch.hypothesis} | {epoch.status} | "
            f"{epoch.evaluation.objective_gain * 100:+.1f}% |"
        )
    uniform, export_led = epochs
    lines += [
        "",
        "## What the loop learned",
        "",
        "- **Uniform 16.4 percent growth was discarded.** Export growth is not a",
        "  company-wide rate. Applying it to Australian aftermarket overstates",
        f"  revenue error from {uniform.evaluation.champion_metrics['revenue_error'] * 100:.1f}%",
        f"  to {uniform.evaluation.challenger_metrics['revenue_error'] * 100:.1f}%.",
        "- **Export-led volume plus 150bps margin compression is proposed.**",
        "  It stays unpromoted until a human accepts the cost-pressure hypothesis.",
        "",
        "| Metric | Flat FY2024 champion | Export-led challenger |",
        "|---|--:|--:|",
    ]
    labels = {
        "revenue_error": "Revenue error",
        "gross_profit_error": "Gross profit error",
        "ebitda_error": "EBITDA error",
    }
    for metric, label in labels.items():
        lines.append(
            f"| {label} | "
            f"{export_led.evaluation.champion_metrics[metric] * 100:.1f}% | "
            f"{export_led.evaluation.challenger_metrics[metric] * 100:.1f}% |"
        )
    lines.append("")
    return "\n".join(lines)


def phase_c() -> str:
    # build_forecast returns both years and README.md calls Phase C an FY2026 to
    # FY2027 forecast, so report both. Reporting FY2026 alone left the second
    # forecast year with no way for a reader to inspect it.
    forecast, segs = am.build_forecast()
    years = {"FY2026": forecast.iloc[:12], "FY2027": forecast.iloc[12:]}
    sections = [to_briefing_md(
        forecast, title="ARB Corporation FY2026 to FY2027 forecast"
    ).rstrip("\n")]
    for year, frame in years.items():
        sections.append("\n".join([
            "",
            f"## {year}",
            "",
            f"- **Revenue:** ${frame['revenue'].sum():,.0f}",
            f"- **EBITDA:** ${frame['ebitda'].sum():,.0f}",
            f"- **Net income:** ${frame['net_income'].sum():,.0f}",
            f"- **Ending cash:** ${frame['ending_cash'].iloc[-1]:,.0f}",
            "",
            f"### Channel mix ({year})",
            "",
            "| Channel | Net sales |",
            "|---|--:|",
            *(f"| {segment.name} | ${segment.net_sales:,.0f} |"
              for segment in segs[year]),
        ]))
    sections.append("\n".join([
        "",
        "Assumptions are in `arb_model.FORECAST`. This is the August 2025 4E",
        "view, not a later refresh. Property capex is stepped down because the",
        "board said FY2026 property investment would be significantly lower.",
        "",
    ]))
    return "\n".join(sections)


def phase_d() -> str:
    grid = am.cost_pressure_sensitivity()
    lines = [
        "# Phase D - Thai Baht / US tariff sensitivity",
        "",
        "Labeled sensitivity, not a kernel FX or customs engine. Adds 150bps",
        "to FY2026 COGS versus the base forecast.",
        "",
        "| Scenario | FY2026 EBITDA | FY2026 FCF |",
        "|---|--:|--:|",
    ]
    for name, row in grid.iterrows():
        lines.append(
            f"| {name} | ${row['fy2026_ebitda']:,.0f} | ${row['fy2026_fcf']:,.0f} |"
        )
    lines.append("")
    return "\n".join(lines)


def run_arb(
    output_dir: str | Path | None = None,
    *,
    replace_epochs: bool = False,
) -> dict:
    """Run Phases A-D and return the FY2026 headline figures.

    ``output_dir`` takes the 4 markdown files and the research memory
    together, so a caller that redirects it writes nothing into the tracked
    example. Omitting it keeps the committed layout: markdown under
    ``output/``, memory under ``.fpa/research/``.

    Research epochs are written exclusively, so replaying into the committed
    layout stops at the epochs this example already ships. ``replace_epochs``
    rewrites them in place; it exists to regenerate this example, and a real
    company workspace should never use it.
    """
    out = Path(output_dir) if output_dir is not None else OUT
    research = RESEARCH if output_dir is None else out / ".fpa" / "research"
    out.mkdir(parents=True, exist_ok=True)
    (out / "reconciliation.md").write_text(phase_a())
    (out / "historical-holdout.md").write_text(phase_b())
    (out / "forecast-briefing.md").write_text(phase_c())
    (out / "sensitivity.md").write_text(phase_d())
    # Phase B's verdicts belong in company memory, not only in the markdown:
    # the registry's challenger names its source epoch, and the research skill
    # tells the next agent to read prior epochs before repeating a hypothesis.
    save_research_objective(am.HOLDOUT_OBJECTIVE, research / "objective.yaml")
    for epoch in am.historical_research_epochs():
        save_epoch(epoch, research, overwrite=replace_epochs)
    forecast, _ = am.build_forecast()
    return {
        "fy2026_revenue": round(float(forecast.iloc[:12]["revenue"].sum())),
        "fy2026_net_income": round(float(forecast.iloc[:12]["net_income"].sum())),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=run_arb.__doc__)
    parser.add_argument(
        "--output-dir",
        help="write the markdown and research memory here instead of the tracked example",
    )
    parser.add_argument(
        "--replace-epochs",
        action="store_true",
        help="rewrite existing research epochs instead of refusing to overwrite them",
    )
    args = parser.parse_args()
    figures = run_arb(args.output_dir, replace_epochs=args.replace_epochs)
    print(f"Wrote Phase A-D markdown to {args.output_dir or 'examples/arb/output/'}")
    for key, value in figures.items():
        print(f"  {key}: {value}")
