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
