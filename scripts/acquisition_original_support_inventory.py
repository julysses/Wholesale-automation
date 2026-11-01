"""Inventory the disposable review lifecycle catalog before renewal migrations.

Run through scripts/run_offline_tests.py; never accepts a production URL.
"""
import json
from acquisition_effective_handoff_tests import EffectiveHandoffTests
from test_acquisition_workspace import main,ROOT
class Inventory(EffectiveHandoffTests):
 def test_inventory(self):
  tables="('acquisition_contract_transitions','acquisition_contract_reviews','acquisition_disposition_plans','acquisition_contract_versions','deals')"
  value={}
  queries={
   'columns':f"SELECT table_schema,table_name,column_name,data_type,is_nullable,column_default,is_generated FROM information_schema.columns WHERE table_schema='public' AND table_name IN {tables} ORDER BY table_name,ordinal_position",
   'constraints':f"SELECT c.relname,co.conname,pg_get_constraintdef(co.oid) definition FROM pg_constraint co JOIN pg_class c ON c.oid=co.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN {tables} ORDER BY 1,2",
   'indexes':f"SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND tablename IN {tables} ORDER BY 1,2",
   'policies':f"SELECT * FROM pg_policies WHERE schemaname='public' AND tablename IN {tables} ORDER BY tablename,policyname",
   'grants':f"SELECT table_name,grantee,privilege_type FROM information_schema.role_table_grants WHERE table_schema='public' AND table_name IN {tables} ORDER BY 1,2,3",
   'triggers':f"SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid) definition FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid WHERE NOT t.tgisinternal AND c.relname IN {tables} ORDER BY 1,2"}
  for name,query in queries.items():value[name]=json.loads(self.sql(f"SELECT coalesce(jsonb_agg(to_jsonb(x)),'[]') FROM ({query}) x"))
  value['row_security']=json.loads(self.sql("SELECT jsonb_agg(to_jsonb(x)) FROM (SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN "+tables+") x"))
  value['migration_manifest']=json.loads((ROOT/'docs/acquisition-automation/evidence/acquisition-upgrade-manifest.json').read_text())
  value['scope']='Disposable EffectiveHandoffTests fixture through 20261101113021; manifest retained as migration reference, not an assertion of full populated upgrade; no production query'
  self.assertTrue(all(row['relrowsecurity'] for row in value['row_security']))
  self.assertEqual(len(value['row_security']),5)
  for grant in value['grants']:
   if grant['table_name']=='acquisition_contract_reviews' and grant['grantee'] in ('anon','authenticated','service_role'):
    self.assertEqual((grant['grantee'],grant['privilege_type']),('authenticated','SELECT'))
  self.assertTrue(any(t['relname']=='acquisition_contract_reviews' and t['tgname']=='acquisition_contract_review_immutable' for t in value['triggers']))
  (ROOT/'docs/acquisition-automation/evidence/2026-11-01-original-support-local-catalog.json').write_text(json.dumps(value,indent=2)+'\n')
if __name__=='__main__':
 raise SystemExit(main(Inventory,['test_inventory']))
