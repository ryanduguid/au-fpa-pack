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
