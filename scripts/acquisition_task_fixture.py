"""Restore inspected tasks before acquisition boundary migrations in local QA.

County-ingestion incoming FK tables are cataloged but not recreated here; full
production upgrade/dependency acceptance must exercise those seven callers too.
"""
import json
from pathlib import Path
from acquisition_call_fixture import install_inspected_table_fixture

CATALOG = Path(__file__).resolve().parents[1]/'docs/acquisition-automation/evidence/2026-10-26-inbound-task-catalog.json'


def install_task_fixture(sql):
    install_inspected_table_fixture(sql, json.loads(CATALOG.read_text()), 'tasks')
