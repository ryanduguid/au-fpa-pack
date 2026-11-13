# Excel export failure handling

`model_to_excel` and `forecast_to_excel` build their workbook in a temporary
directory beside the destination. They close the file before replacing the
destination, so failed serialisation or replacement retains the previous report.
The model exporter also opens and closes the staged archive before replacement;
an inspection failure retains the previous report and returns the CLI's export
failure response.
An Excel file held open on Windows can block replacement; the export raises the
error and removes its staging files.

Existing symlinks retain their target semantics. On POSIX systems, replacement
preserves the destination's permission bits. Replacing a file changes its inode;
other hard links continue to contain the previous report. These exports provide
atomic replacement on the destination filesystem, without a power-loss durability
guarantee. The destination's parent directory must already exist.

Briefings reject missing or non-finite financial values, including runway cash
and overflowing headline totals. Integer headlines and monthly rows retain their
whole-dollar values without int64 wraparound or conversion to floating point.
Forecast exports reject missing cells and non-finite numbers before creating
staging files; text labels remain supported. These checks preserve the existing
report when the proposed values are invalid. Excel's numeric precision limits
still apply to finite values written to the workbook.

The model exporter retains its Assumptions and Model sheets and their formulas.
The forecast exporter retains its Forecast sheet. Run the usual structure and
formula verification before relying on a workbook; a completed file write does
not establish accounting correctness.

The standard model workbook includes a direct cash check built from sales,
receivables, inventory, payables and cash costs. It can detect an omitted
D&A addback, tax payment, capex or principal payment even when the profit
bridge and ending cash carry that error together. Harbour Light adds its
non-cash leave provision and accrued GST less settlements to the check.
The check shares the model’s source balances and costs; it is not an external
bank reconciliation. Verification requires non-empty expected data and a
finite, non-negative tolerance, including zero for an exact comparison.

`check_direct_cash` shows the raw dollar difference. For positive tolerances,
verification also allows the small `direct_cash_rounding` amount. This is
`4e-15` times the sum of the absolute shared source amounts on both paths,
including both D&A occurrences and current/prior working capital balances.
Each amount is scaled before summing to avoid an overflowing gross total.
The coefficient bounds rounding across 2 binary64 addition/subtraction paths
of depth at most 16; changes to those paths need that bound reassessed.
Harbour Light includes its leave and GST amounts. Differences within this
allowance cannot be distinguished from roundoff. The allowance must be finite
and non-negative, and does not scale with the caller's tolerance. The previous
3 checks keep their absolute tolerance; zero tolerance permits no allowance.
