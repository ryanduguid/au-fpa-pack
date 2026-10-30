import hashlib
import json

import yaml

from pyfpa.analysis.assumptions import assumption_report
from pyfpa.config.schemas import EntityConfig


def config(**changes):
    return EntityConfig.model_validate({
        'name': 'Synthetic Co', 'start_month': '2026-07', 'tax_rate': 0.25,
        'channels': [{'name': 'Retail', 'annual_revenue': 1200, 'cogs_pct': 0.4, 'seasonality': [1.0] * 12}],
        'working_capital': {'dso_days': 30, 'dpo_days': 30, 'dio_days': 0},
        **changes,
    })


def test_defaults_and_explicit_zero_have_distinct_origins():
    report = assumption_report(config(capex_monthly=0))
    rows = {row['path']: row for row in report['assumptions']}
    assert rows['/capex_monthly']['origin'] == 'supplied'
    assert rows['/da_monthly']['origin'] == 'default'
    assert rows['/opening_balances/cash']['origin'] == 'default'
    assert rows['/channels/Retail/growth_rate']['origin'] == 'default'
    assert report['methods']['receipts'] == 'DSO days'
    assert report['requires_review'] is True


def test_changes_use_line_names_and_preserve_origin_changes():
    old = config()
    new = config(capex_monthly=0, channels=[
        {'name': 'Wholesale', 'annual_revenue': 600, 'cogs_pct': 0.2, 'seasonality': [1.0] * 12},
        {'name': 'Retail', 'annual_revenue': 1800, 'cogs_pct': 0.4, 'seasonality': [1.0] * 12},
    ])
    rows = {row['path']: row for row in assumption_report(new, old)['assumptions']}
    assert rows['/capex_monthly']['change'] == 'changed'
    assert rows['/channels/Retail/annual_revenue']['previous_value'] == 1200
    assert rows['/channels/Wholesale/annual_revenue']['change'] == 'added'
    assert rows['/tax_rate']['change'] == 'unchanged'


def test_collection_and_tax_methods_and_comparison_scope():
    cfg = config(working_capital={'collection_profile': [0.5, 0.5], 'dpo_days': 30, 'dio_days': 0},
                 income_tax={'forecast_losses_deductible': False})
    report = assumption_report(cfg, config(name='Other synthetic entity', horizon_months=24))
    assert report['methods']['receipts'] == 'Collection profile'
    assert report['methods']['income_tax'] == 'Income-year provision with explicit cash payments'
    assert report['scope_changes'] == ['name', 'horizon_months']
    assert report['method_changes'] == ['receipts', 'income_tax']
    assert report['comparable'] is False


def test_assumption_cli_reports_hashes_without_writing_config(tmp_path, run_cli):
    source = tmp_path / 'config.yaml'
    raw = yaml.safe_dump(config().model_dump()).encode()
    source.write_bytes(raw)
    run_cli('init', str(tmp_path), '--business-name', 'Synthetic Co')
    result = run_cli('model-assumptions', str(tmp_path), '--config', str(source), '--previous-config', str(source))
    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)['data']
    assert data['config_sha256'] == data['previous_config_sha256']
    assert all(row['change'] == 'unchanged' for row in data['assumptions'])
    assert source.read_bytes() == raw


def test_malformed_yaml_is_a_controlled_cli_failure(tmp_path, run_cli):
    source = tmp_path / 'bad.yaml'
    source.write_text('channels: [', encoding='utf-8')
    run_cli('init', str(tmp_path), '--business-name', 'Synthetic Co')
    result = run_cli('model-assumptions', str(tmp_path), '--config', str(source))
    assert result.returncode == 1
    assert json.loads(result.stdout)['error']['type'] == 'invalid_config'


def test_containers_report_empty_lists_null_models_and_explicit_empty_objects():
    rent = {'name': 'Rent', 'kind': 'fixed', 'monthly_amount': 100}
    rows = {row['path']: row for row in assumption_report(
        config(opex=[rent], income_tax={}), config(opex=[]))['assumptions']}
    assert rows['/opex']['change'] == 'changed'
    assert rows['/opex']['value'] == ['Rent'] and rows['/opex']['previous_value'] == []
    assert rows['/opex/Rent/monthly_amount']['change'] == 'added'
    assert rows['/income_tax']['previous_value'] is None and rows['/income_tax']['change'] == 'changed'
    assert rows['/income_tax']['origin'] == 'supplied'
    assert not [path for path, row in rows.items() if row['change'] == 'removed']
    rows = {row['path']: row for row in assumption_report(config(opening_balances={}))['assumptions']}
    assert rows['/opening_balances']['origin'] == 'supplied'
    assert rows['/opening_balances/cash']['origin'] == 'default'
    assert {row['path']: row for row in assumption_report(config())['assumptions']}[
        '/opening_balances']['origin'] == 'default'


def test_payment_months_are_compared_individually():
    old = config(income_tax={'payments': {'2026-10': 100.0, '2027-01': 50.0}})
    new = config(income_tax={'payments': {'2026-10': 120.0, '2027-04': 50.0}})
    rows = {row['path']: row for row in assumption_report(new, old)['assumptions']}
    assert rows['/income_tax/payments/2026-10']['change'] == 'changed'
    assert rows['/income_tax/payments/2027-01']['change'] == 'removed'
    assert rows['/income_tax/payments/2027-04']['change'] == 'added'


def test_minimal_yaml_reports_defaults_and_the_digest_of_the_parsed_bytes(tmp_path, run_cli):
    source = tmp_path / 'minimal.yaml'
    raw = (b"name: Synthetic Co\r\nstart_month: '2026-07'\r\ntax_rate: 0.25\r\nchannels:\r\n"
           b"  - {name: Retail, annual_revenue: 1200, cogs_pct: 0.4, seasonality: [1,1,1,1,1,1,1,1,1,1,1,1]}\r\n"
           b"working_capital: {dso_days: 30, dpo_days: 30, dio_days: 0}\r\n")
    source.write_bytes(raw)
    run_cli('init', str(tmp_path), '--business-name', 'Synthetic Co')
    result = run_cli('model-assumptions', str(tmp_path), '--config', str(source))
    assert result.returncode == 0, result.stdout
    data = json.loads(result.stdout)['data']
    rows = {row['path']: row for row in data['assumptions']}
    assert rows['/da_monthly']['origin'] == 'default'
    assert rows['/tax_rate']['origin'] == 'supplied'
    assert data['config_sha256'] == hashlib.sha256(raw).hexdigest()


def test_deeply_nested_yaml_is_a_controlled_cli_failure(tmp_path, run_cli):
    source = tmp_path / 'deep.yaml'
    source.write_text('channels: ' + '[' * 20000 + ']' * 20000, encoding='utf-8')
    run_cli('init', str(tmp_path), '--business-name', 'Synthetic Co')
    result = run_cli('model-assumptions', str(tmp_path), '--config', str(source))
    assert result.returncode == 1
    assert json.loads(result.stdout)['error']['type'] == 'invalid_config'


def test_reordered_named_lines_are_unchanged():
    retail = {'name': 'Retail', 'annual_revenue': 1200, 'cogs_pct': 0.4, 'seasonality': [1.0] * 12}
    wholesale = {'name': 'Wholesale', 'annual_revenue': 600, 'cogs_pct': 0.2, 'seasonality': [1.0] * 12}
    rent = {'name': 'Rent', 'kind': 'fixed', 'monthly_amount': 100}
    ads = {'name': 'Ads', 'kind': 'variable', 'pct_of_revenue': 0.05}
    loan = {'name': 'Loan', 'kind': 'term_loan', 'opening_balance': 1000, 'annual_rate': 0.08}
    card = {'name': 'Card', 'kind': 'loc', 'opening_balance': 0, 'annual_rate': 0.2}
    old = config(channels=[retail, wholesale], opex=[rent, ads], debt=[loan, card])
    new = config(channels=[wholesale, retail], opex=[ads, rent], debt=[card, loan])
    report = assumption_report(new, old)
    assert {row['change'] for row in report['assumptions']} == {'unchanged'}
