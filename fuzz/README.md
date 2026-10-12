The Atheris target writes fabricated bytes to a CSV file and reads it with the
Xero report importer, in both of its modes, and with the two-column P&L reader.
A malformed export must be refused with `ValueError`, and every amount an
importer accepts must be finite. Unexpected exceptions and failed invariants
fail the run. The seed corpus holds the package's Xero and QuickBooks fixtures,
truncated to 4 KiB, and two small exports.

On Linux with Python 3.14, from the repository root, run:

```sh
python -m pip install --require-hashes --only-binary :all: -r requirements-fuzz.txt
python -m fuzz.xero_import fuzz/corpus -max_total_time=60 -max_len=4096 -timeout=2 -rss_limit_mb=1024
```

`requirements-fuzz.txt` pins Atheris and the runtime dependencies at their
`uv.lock` versions, so the harness imports `pyfpa` from the checkout. CI runs
the target after main pushes, weekly and on demand, with read-only repository
access and a five-minute timeout. `tests/test_fuzz_harness.py` replays the
corpus on every supported platform. Atheris does not support Windows, so
coverage-guided fuzzing runs on Linux. A successful run is bounded evidence,
not proof that every input is handled.

After changing a pinned version in `requirements-fuzz.in`, regenerate the
hashes with:

```sh
uv pip compile requirements-fuzz.in --python-version 3.14 --python-platform x86_64-unknown-linux-gnu --generate-hashes --output-file requirements-fuzz.txt
```
