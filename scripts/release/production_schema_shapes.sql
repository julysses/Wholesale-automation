BEGIN READ ONLY;
SET LOCAL search_path=public,extensions;
WITH app_tables AS (
 SELECT c.*,n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname IN ('public','private','wholesale_ingest','offer_review') AND c.relkind IN ('r','p')
 AND NOT EXISTS(SELECT 1 FROM pg_depend d WHERE d.classid='pg_class'::regclass AND d.objid=c.oid AND d.deptype='e')
)
SELECT jsonb_build_object(
 'captured_at',now(),
 'server_version',current_setting('server_version_num'),
 'tables',(SELECT jsonb_agg(jsonb_build_object(
 'schema',t.nspname,'name',t.relname,'acl',t.relacl::text,'rls',t.relrowsecurity,'force_rls',t.relforcerowsecurity,
 'columns',(SELECT jsonb_agg(jsonb_build_object('name',a.attname,'type',format_type(a.atttypid,a.atttypmod),
 'default',pg_get_expr(ad.adbin,ad.adrelid),'notnull',a.attnotnull,'identity',a.attidentity,'generated',a.attgenerated) ORDER BY a.attnum)
 FROM pg_attribute a LEFT JOIN pg_attrdef ad ON ad.adrelid=a.attrelid AND ad.adnum=a.attnum WHERE a.attrelid=t.oid AND a.attnum>0 AND NOT a.attisdropped)) ORDER BY t.nspname,t.relname) FROM app_tables t),
 'constraints',(SELECT jsonb_agg(jsonb_build_object('schema',t.nspname,'table',t.relname,'name',c.conname,'type',c.contype,'definition',pg_get_constraintdef(c.oid)) ORDER BY t.nspname,t.relname,c.conname)
 FROM pg_constraint c JOIN app_tables t ON t.oid=c.conrelid),
 'indexes',(SELECT jsonb_agg(pg_get_indexdef(i.indexrelid) ORDER BY i.indexrelid::regclass::text) FROM pg_index i JOIN app_tables t ON t.oid=i.indrelid WHERE NOT EXISTS(SELECT 1 FROM pg_constraint c WHERE c.conindid=i.indexrelid)),
 'triggers',(SELECT jsonb_agg(pg_get_triggerdef(tr.oid) ORDER BY tr.oid::text) FROM pg_trigger tr JOIN app_tables t ON t.oid=tr.tgrelid WHERE NOT tr.tgisinternal),
 'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.schemaname,p.tablename,p.policyname) FROM pg_policies p WHERE p.schemaname IN ('public','private','wholesale_ingest','offer_review')),
 'views',(SELECT jsonb_agg(jsonb_build_object('schema',n.nspname,'name',c.relname,'definition',pg_get_viewdef(c.oid,false)) ORDER BY n.nspname,c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','private','wholesale_ingest','offer_review') AND c.relkind='v'),
 'view_security',(SELECT jsonb_agg(jsonb_build_object('schema',n.nspname,'name',c.relname,'options',c.reloptions,'acl',c.relacl::text) ORDER BY n.nspname,c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','private','wholesale_ingest','offer_review') AND c.relkind='v'),
 'schema_acls',(SELECT jsonb_agg(jsonb_build_object('schema',nspname,'acl',nspacl::text) ORDER BY nspname) FROM pg_namespace WHERE nspname IN ('public','private','wholesale_ingest','offer_review')),
 'default_acls',(SELECT jsonb_agg(jsonb_build_object('schema',n.nspname,'owner',pg_get_userbyid(d.defaclrole),'type',d.defaclobjtype,'acl',d.defaclacl::text) ORDER BY n.nspname,d.defaclobjtype,pg_get_userbyid(d.defaclrole)) FROM pg_default_acl d JOIN pg_namespace n ON n.oid=d.defaclnamespace WHERE n.nspname IN ('public','private','wholesale_ingest','offer_review'))
) evidence;
COMMIT;
