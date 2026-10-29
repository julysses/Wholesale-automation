"""Disposable catalog-shaped Storage SQL fixture, not an HTTP/object-store emulator."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORAGE_MIGRATION = ROOT/'frontend/supabase/migrations/20261029024603_acquisition_evidence_storage.sql'


def install_storage_fixture(sql):
    statements = []
    def append_sql(statement):
        statements.append(statement+";")

    catalog = json.loads((ROOT/'docs/acquisition-automation/evidence/2026-10-29-evidence-catalog.json').read_text())
    append_sql("CREATE SCHEMA storage; CREATE TYPE storage.buckettype AS ENUM ('STANDARD','ANALYTICS','VECTOR'); "
        "GRANT USAGE ON SCHEMA storage,auth TO anon,authenticated,service_role;")
    for table in ('buckets','objects'):
        columns = []
        for c in catalog['columns']:
            if c['schema']=='storage' and c['table']==table:
                dtype = 'text[]' if c['type']=='_text' else 'storage.buckettype' if c['type']=='buckettype' else c['type']
                columns.append('"'+c['column']+'" '+dtype+(' DEFAULT '+c['default'] if c['default'] else '')+
                               (' NOT NULL' if c['nullable']=='NO' else ''))
        append_sql(f'CREATE TABLE storage.{table}('+','.join(columns)+')')
        for c in catalog['constraints']:
            if c['schema']=='storage' and c['table']==table:
                append_sql(f'ALTER TABLE storage.{table} ADD CONSTRAINT "{c["name"]}" '+c['definition'])
        for i in catalog['indexes']:
            if i['schema']=='storage' and i['table']==table and '_pkey ' not in i['definition']:
                append_sql(i['definition'])
        append_sql(f'ALTER TABLE storage.{table} ENABLE ROW LEVEL SECURITY; '
            f'GRANT SELECT,INSERT,UPDATE,DELETE ON storage.{table} TO anon,authenticated; '
            f'GRANT ALL ON storage.{table} TO service_role;')
    # Same operation setting/normalization as inspected live platform helpers.
    append_sql("""CREATE FUNCTION storage.operation() RETURNS text LANGUAGE plpgsql STABLE AS $$
      BEGIN RETURN current_setting('storage.operation',true); END $$;
      CREATE FUNCTION storage.allow_any_operation(expected_operations text[]) RETURNS boolean LANGUAGE sql STABLE AS $$
       WITH current_operation AS (SELECT storage.operation() AS raw_operation), normalized AS (
        SELECT CASE WHEN raw_operation LIKE 'storage.%' THEN substr(raw_operation,9) ELSE raw_operation END AS current_operation
        FROM current_operation)
       SELECT EXISTS(SELECT 1 FROM normalized n CROSS JOIN LATERAL unnest(expected_operations) AS expected_operation
        WHERE expected_operation IS NOT NULL AND expected_operation<>'' AND n.current_operation=
        CASE WHEN expected_operation LIKE 'storage.%' THEN substr(expected_operation,9) ELSE expected_operation END)
      $$;
      CREATE FUNCTION storage.allow_only_operation(expected_operation text) RETURNS boolean LANGUAGE sql STABLE AS $$
       SELECT storage.allow_any_operation(ARRAY[expected_operation]) $$;
      INSERT INTO storage.buckets(id,name) VALUES('legacy-fixture','legacy-fixture');
      INSERT INTO storage.objects(bucket_id,name,metadata) VALUES('legacy-fixture','sentinel','{"preserved":true}');
    """)

    sql("\n".join(statements))
