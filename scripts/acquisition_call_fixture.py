"""Restore inspected call_events before boundary migrations in disposable QA.

No production connection or rows. Other inspected call tables remain outside this
focused fixture until their qualification/appointment dependency chain is restored.
"""
import json
from pathlib import Path
from acquisition_campaign_fixture import quote

CATALOG = Path(__file__).resolve().parents[1]/'docs/acquisition-automation/evidence/2026-10-26-inbound-call-catalog.json'


def install_call_fixture(sql):
    catalog = json.loads(CATALOG.read_text())
    table = 'call_events'
    columns = []
    for row in catalog['columns']:
        if row['table_name'] != table:
            continue
        expression = row['expression']
        suffix = ' DEFAULT '+expression if expression else ''
        columns.append(quote(row['column_name'])+' '+row['data_type']+suffix+(' NOT NULL' if row['not_null'] else ''))
    sql('CREATE TABLE public.call_events('+','.join(columns)+'); ALTER TABLE public.call_events ENABLE ROW LEVEL SECURITY;')
    for row in catalog['constraints']:
        if row['table_name'] == table:
            sql('ALTER TABLE public.call_events ADD CONSTRAINT '+quote(row['conname'])+' '+row['definition']+';')
    for row in catalog['policies']:
        if row['tablename'] != table:
            continue
        statement='CREATE POLICY '+quote(row['policyname'])+' ON public.call_events AS '+row['permissive']+' FOR '+row['cmd']+' TO '+','.join(quote(role) for role in row['roles'])
        if row['qual']:statement+=' USING ('+row['qual']+')'
        if row['with_check']:statement+=' WITH CHECK ('+row['with_check']+')'
        sql(statement+';')
    for row in catalog['grants']:
        if row['table_name']==table and row['grantee'] in ('anon','authenticated','service_role'):
            sql('GRANT '+row['privilege_type']+' ON public.call_events TO '+quote(row['grantee'])+';')
    constraint_names={row['conname'] for row in catalog['constraints']}
    for row in catalog['indexes']:
        if row['table_name']==table and row['index_name'] not in constraint_names:
            sql(row['definition']+';')
