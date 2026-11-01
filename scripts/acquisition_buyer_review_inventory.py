"""Disposable current catalog inventory for buyer evidence/review design; no schema edits."""
import hashlib
import json
from pathlib import Path
from acquisition_buyer_catalog_inventory import main


def inspect(db):
    tables = db.query("""SELECT n.nspname AS schema,c.relname AS name,c.relrowsecurity,c.relforcerowsecurity,
        pg_get_userbyid(c.relowner) AS owner,c.relacl::text AS acl
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE c.relkind IN ('r','p') AND ((n.nspname IN ('public','private') AND
          (c.relname LIKE '%buyer%' OR c.relname LIKE 'acquisition_evidence%' OR c.relname LIKE 'acquisition_contract%'
           OR c.relname IN ('deal_matches','buyer_outreach_log','deals','tasks')))
          OR (n.nspname='storage' AND c.relname IN ('objects','buckets')))
        ORDER BY 1,2""")
    qualified = [row['schema']+'.'+row['name'] for row in tables]
    queries = {
        'columns': "SELECT table_schema,table_name,column_name,data_type,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema||'.'||table_name=ANY(%s) ORDER BY 1,2,ordinal_position",
        'constraints': "SELECT n.nspname,c.relname,co.conname,co.contype,pg_get_constraintdef(co.oid) AS definition FROM pg_constraint co JOIN pg_class c ON c.oid=co.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname||'.'||c.relname=ANY(%s) ORDER BY 1,2,3",
        'indexes': "SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes WHERE schemaname||'.'||tablename=ANY(%s) ORDER BY 1,2,3",
        'policies': "SELECT * FROM pg_policies WHERE schemaname||'.'||tablename=ANY(%s) ORDER BY schemaname,tablename,policyname",
        'grants': "SELECT table_schema,table_name,grantee,privilege_type FROM information_schema.role_table_grants WHERE table_schema||'.'||table_name=ANY(%s) ORDER BY 1,2,3,4",
        'triggers': "SELECT n.nspname,c.relname,t.tgname,pg_get_triggerdef(t.oid) AS definition FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE NOT t.tgisinternal AND n.nspname||'.'||c.relname=ANY(%s) ORDER BY 1,2,3",
        'incoming_foreign_keys': "SELECT n.nspname,c.relname,co.conname,pg_get_constraintdef(co.oid) AS definition FROM pg_constraint co JOIN pg_class c ON c.oid=co.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_class target ON target.oid=co.confrelid JOIN pg_namespace tn ON tn.oid=target.relnamespace WHERE co.contype='f' AND tn.nspname||'.'||target.relname=ANY(%s) ORDER BY 1,2,3",
    }
    result = {'tables':tables, **{key:db.query(sql,[qualified]) for key,sql in queries.items()}}
    result['functions'] = db.query("""SELECT n.nspname,p.proname,p.oid::regprocedure::text AS signature,
      pg_get_functiondef(p.oid) AS definition,pg_get_userbyid(p.proowner) AS owner,p.prosecdef AS security_definer,
      p.proacl::text AS acl,p.proconfig AS settings FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
      WHERE p.prokind='f' AND n.nspname IN ('public','private') AND
      (p.prosrc ILIKE '%acquisition_evidence%' OR p.prosrc ILIKE '%acquisition_buyer%' OR p.proname LIKE '%contract%scan%') ORDER BY 1,2,3""")
    manifest = Path('docs/acquisition-automation/evidence/acquisition-upgrade-manifest.json').read_bytes()
    result.update(scope='Disposable full baseline plus118 inventory for buyer evidence/review; not production or migration-role acceptance',
        manifest_sha256=hashlib.sha256(manifest).hexdigest(), migration_count=len(json.loads(manifest)['migrations']),production_changed=False)
    path = Path('docs/acquisition-automation/evidence/2026-11-01-buyer-review-local-catalog.json')
    path.write_text(json.dumps(result,indent=2,default=str)+'\n')
    print(json.dumps({'evidence':str(path),'counts':{key:len(value) for key,value in result.items() if isinstance(value,list)}}))


if __name__ == '__main__':
    main(inspect)
