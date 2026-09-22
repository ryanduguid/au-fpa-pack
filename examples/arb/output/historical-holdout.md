# Phase B - FY2025 retrospective scenario comparison

The champion is a flat FY2024 run rate, scored against FY2025 actuals.
The challengers use FY2025 realised export growth, rounded to 16.4%,
as an input. The figure comes from data/segments.csv and the Appendix 4E
cited in data/SOURCES.md. FY2025 is therefore not an independent holdout.
The 0.1% revenue error measures retrospective fit, not forecasting accuracy.
Validate on a separate period with inputs fixed before that period before promotion.
Working-capital days are not a holdout metric: AR barely moved while
sales grew, and H2 destocking is a management action.

| Epoch | Hypothesis | Status | Objective gain |
|---|---|---|--:|
| arb-fy2025-001-uniform-export-rate | Apply FY2025 realised export growth of 16.4% to every sales channel and hold FY2024 EBITDA margin. | discarded | -100.1% |
| arb-fy2025-002-export-led-margin-pressure | Use FY2025 realised export growth of 16.4%; Australian aftermarket and OEM stay flat, and EBITDA margin compresses 150bps on THB and tariff cost pressure known as a 2025 risk. | discarded | +89.8% |

## What the loop learned

- **Uniform 16.4% growth was discarded.** Export growth is not a
  company-wide rate. Applying it to Australian aftermarket overstates
  revenue error from 5.0%
  to 10.5%.
- **Export-led volume plus 150bps margin compression is discarded.**
  Its better retrospective fit does not pass the holdout-separation check.
  A separate evaluation period is required before promotion.

| Metric | Flat FY2024 champion | Export-led challenger |
|---|--:|--:|
| Revenue error | 5.0% | 0.1% |
| Gross profit error | 4.2% | 1.0% |
| EBITDA error | 0.9% | 0.1% |
