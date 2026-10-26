"""Restore inspected campaign dependencies inside disposable acquisition tests only.

Uses a checked-in metadata-only catalog, never a connection or production rows.
Call before acquisition boundary migrations so their catalog scans see these tables.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT/'docs/acquisition-automation/evidence/2026-10-26-campaign-catalog.json'
TABLES = ('ad_campaigns', 'ad_creatives', 'lead_form_configs', 'fb_campaigns', 'fb_ad_sets', 'fb_campaign_performance')
COST_CATALOG = ROOT/'docs/acquisition-automation/evidence/2026-10-26-cost-catalog.json'


def quote(value):
    return '"'+value.replace('"','""')+'"'


def install_campaign_fixture(sql):
    catalog = json.loads(CATALOG.read_text())
    costs = json.loads(COST_CATALOG.read_text())
    for key in ('columns','constraints','policies','grants','triggers'):
        catalog[key].extend(costs[key])
    sql("CREATE FUNCTION public.is_approved() RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER "
        "SET search_path TO public,pg_temp AS $$ SELECT EXISTS(SELECT 1 FROM profiles WHERE id=auth.uid() AND status='approved') $$; "
        "CREATE FUNCTION public.update_updated_at_column() RETURNS trigger LANGUAGE plpgsql "
        "SET search_path TO pg_catalog,public,pg_temp AS $$ BEGIN NEW.updated_at=NOW(); RETURN NEW; END $$; "
        "GRANT USAGE ON SCHEMA public TO anon;")
    for table in TABLES:
        columns=[]
        for column in catalog['columns']:
            if column['table_name']!=table:
                continue
            expression=column['expression']
            if expression:
                expression=expression.replace('\\n', '\n')
            suffix=(f' GENERATED ALWAYS AS ({expression}) STORED' if column['generated']=='s'
                    else ' DEFAULT '+expression if expression else '')
            columns.append(quote(column['column_name'])+' '+column['data_type']+suffix+(' NOT NULL' if column['not_null'] else ''))
        sql('CREATE TABLE public.'+quote(table)+'('+','.join(columns)+');')
    # Restore the FK edges previously omitted because these parent tables were
    # absent. Retell/recovery tables remain outside this focused fixture.
    for constraint in sorted(catalog['constraints'], key=lambda item: item['definition'].startswith('FOREIGN KEY')):
        if constraint['table_name'] in TABLES or constraint['conname'] in {
                'leads_ad_campaign_id_fkey','leads_ad_creative_id_fkey',
                'leads_form_submission_id_fkey','lead_form_submissions_form_id_fkey'}:
            sql('ALTER TABLE public.'+quote(constraint['table_name'])+' ADD CONSTRAINT '+
                quote(constraint['conname'])+' '+constraint['definition']+';')
    for table in TABLES:
        sql('ALTER TABLE public.'+quote(table)+' ENABLE ROW LEVEL SECURITY;')
    for policy in catalog['policies']:
        if policy['tablename'] not in TABLES:
            continue
        statement='CREATE POLICY '+quote(policy['policyname'])+' ON public.'+quote(policy['tablename'])
        statement+=' AS '+policy['permissive']+' FOR '+policy['cmd']+' TO '+','.join(quote(role) for role in policy['roles'])
        if policy['qual']:statement+=' USING ('+policy['qual']+')'
        if policy['with_check']:statement+=' WITH CHECK ('+policy['with_check']+')'
        sql(statement+';')
    for grant in catalog['grants']:
        if grant['table_name'] in TABLES and grant['grantee'] in ('anon','authenticated','service_role'):
            sql('GRANT '+grant['privilege_type']+' ON public.'+quote(grant['table_name'])+' TO '+quote(grant['grantee'])+';')
    for trigger in catalog['triggers']:
        if trigger['table_name'] in TABLES:
            sql(trigger['definition']+';')

    # Constraint indexes already exist; restore additional inspected indexes.
    for index in costs['indexes']:
        if index['indexname'] not in {row['conname'] for row in costs['constraints']}:
            sql(index['indexdef']+';')
