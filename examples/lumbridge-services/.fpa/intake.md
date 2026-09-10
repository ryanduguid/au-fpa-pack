---
schema_version: 1
business_name: Lumbridge Services
facts:
- key: business_model
  topic: business
  question: What does the company sell, and who are the primary customers?
  answer: Synthetic Newcastle NSW maintenance business serving commercial customers.
    Not a real client.
  status: inferred
  confidence: 1.0
  source_type: local_file
  sources:
  - README.md
  alternatives: []
- key: revenue_model
  topic: business
  question: How is revenue earned and billed, including pricing and payment terms?
  answer: Fabricated September revenue of AUD 60,000 repeats monthly; invoices recognise
    services in the listed month and collect on explicit dates.
  status: inferred
  confidence: 1.0
  source_type: local_file
  sources:
  - README.md
  alternatives: []
- key: customer_channels
  topic: business
  question: Which channels, products, or segments should the model distinguish?
  answer: Varrock maintenance earns AUD 40,000 monthly and Falador repairs AUD 20,000.
    Names are OSRS references only.
  status: inferred
  confidence: 1.0
  source_type: local_file
  sources:
  - README.md
  alternatives: []
- key: collections
  topic: cash_cycle
  question: When do customers usually pay, and what causes collections to vary?
  answer: Opening receivables are AUD 66,000. OPEN-V's AUD 44,000 receipt can move
    by 0 to 120 calendar days; the main comparison uses 45 days.
  status: inferred
  confidence: 1.0
  source_type: local_file
  sources:
  - README.md
  alternatives: []
- key: supplier_payments
  topic: cash_cycle
  question: When are suppliers, payroll, inventory, and other major obligations paid?
  answer: Materials settle the following month. Monthly net wages and super share
    an explicit payday. The CSV schedules tax, overhead and loan payments.
  status: inferred
  confidence: 1.0
  source_type: local_file
  sources:
  - README.md
  alternatives: []
- key: seasonality
  topic: cash_cycle
  question: What is seasonal or lumpy across revenue, costs, inventory, and cash?
  answer: No seasonality or growth is assumed. October includes opening GST and an
    income tax instalment. The receipt-delay scenario changes cash, not profit.
  status: inferred
  confidence: 1.0
  source_type: local_file
  sources:
  - README.md
  alternatives: []
- key: entities
  topic: finance_structure
  question: Which legal entities, currencies, and intercompany relationships matter?
  answer: One fictional NSW-only, ungrouped entity in AUD, with no intercompany balances
    or foreign currency.
  status: inferred
  confidence: 1.0
  source_type: local_file
  sources:
  - README.md
  alternatives: []
- key: financing
  topic: finance_structure
  question: What debt, credit lines, covenants, or other financing is in place?
  answer: AUD 20,000 opening loan, AUD 1,000 monthly principal and an assumed AUD
    200 monthly interest. No overdraft, new borrowing or owner withdrawals.
  status: inferred
  confidence: 1.0
  source_type: local_file
  sources:
  - README.md
  alternatives: []
- key: data_sources
  topic: finance_structure
  question: Which systems and files contain the financial and operating actuals?
  answer: Six fabricated local files in data/, plus the existing effective-dated super
    and payroll-tax tables. The README explains provenance and limits.
  status: inferred
  confidence: 1.0
  source_type: local_file
  sources:
  - README.md
  alternatives: []
- key: planning_cadence
  topic: planning
  question: How often do you close, reforecast, report, and make planning decisions?
  answer: Monthly forecast from October to December 2026, with thirteen weeks from
    2 October to 31 December. An independent trial is prepared but not completed.
  status: inferred
  confidence: 1.0
  source_type: local_file
  sources:
  - README.md
  alternatives: []
- key: cfo_priorities
  topic: planning
  question: Which decisions, risks, or questions matter most to the CFO right now?
  answer: Explain why a profitable quarter can have a cash shortfall; identify liabilities,
    collection timing and funding needed before discretionary equipment spending.
  status: inferred
  confidence: 1.0
  source_type: local_file
  sources:
  - README.md
  alternatives: []
---
