"""Print two fabricated workpapers using the example's public functions."""
import json

from invoice_cash import invoice_cash
from operating_variance import revenue_bridge

invoice = {"id": "I1", "original": "10000", "settled": "4000", "outstanding": "6000",
           "due_date": "2026-10-01", "expected_date": "2026-11-01", "disputed": "1000",
           "apply_to": "", "evidence": "Fabricated invoice and receipt"}
credit = {**invoice, "id": "CN1", "original": "-500", "settled": "0", "outstanding": "-500",
          "disputed": "0", "apply_to": "I1", "evidence": "Fabricated credit allocation"}
print(json.dumps({
    "invoice_book": invoice_cash([invoice, credit], control_balance="5500", cutoff="2026-09-30"),
    "revenue_bridge": revenue_bridge([{
        "service": "Maintenance", "prior_units": "200", "current_units": "220",
        "prior_price": "100", "current_price": "110", "evidence": "Fabricated job register",
    }], "20000", "24150"),
}, indent=2))
