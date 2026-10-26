-- Read-only metadata inventory; no application records or secrets.
-- Run against the explicitly verified project only. This is not a migration.
BEGIN READ ONLY;

-- tables and views
SELECT n.nspname AS schema, c.relname AS name, c.relkind, c.relrowsecurity AS rls, c.relforcerowsecurity AS force_rls FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','private','wholesale_ingest') AND c.relkind IN ('r','p','v','m') ORDER BY 1,2;

-- migration ledger metadata only
SELECT version, name FROM supabase_migrations.schema_migrations ORDER BY version;

-- columns
SELECT table_schema,table_name,column_name,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema IN ('public','private','wholesale_ingest') ORDER BY table_schema,table_name,ordinal_position;

-- constraints
SELECT n.nspname AS schema,c.relname AS table_name,con.conname,con.contype,pg_get_constraintdef(con.oid) AS definition FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','private','wholesale_ingest') ORDER BY 1,2,3;

-- indexes
SELECT schemaname,tablename,indexname,indexdef FROM pg_indexes WHERE schemaname IN ('public','private','wholesale_ingest') ORDER BY 1,2,3;

-- policies
SELECT schemaname,tablename,policyname,permissive,roles,cmd,qual,with_check FROM pg_policies WHERE schemaname IN ('public','private','wholesale_ingest','storage') ORDER BY 1,2,3;

-- triggers
SELECT n.nspname AS schema,c.relname AS table_name,t.tgname,pg_get_triggerdef(t.oid) AS definition FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','private','wholesale_ingest') AND NOT t.tgisinternal ORDER BY 1,2,3;

-- functions
SELECT n.nspname AS schema,p.proname,pg_get_function_identity_arguments(p.oid) AS args,p.prosecdef,p.proconfig,p.proacl FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname IN ('public','private','wholesale_ingest') AND p.prokind='f' ORDER BY 1,2;

-- runtime
SELECT 'cron' AS source,jsonb_build_object('jobname',jobname,'schedule',schedule,'active',active) AS state FROM cron.job UNION ALL SELECT 'retell_sms_scheduler',jsonb_build_object('enabled',enabled) FROM private.retell_sms_scheduler UNION ALL SELECT 'retell_app_scheduler',jsonb_build_object('enabled',enabled,'start_hour',start_hour,'end_hour',end_hour) FROM private.retell_app_scheduler;

-- access
SELECT n.nspname AS schema,c.relname,c.relkind,c.reloptions,c.relacl FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname IN ('public','private','wholesale_ingest') AND c.relkind IN ('r','v','p','m') ORDER BY 1,2;

-- authFunctions
SELECT n.nspname AS schema,p.proname,pg_get_functiondef(p.oid) AS definition FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE (n.nspname='public' AND p.proname IN ('is_approved','is_admin')) OR (n.nspname='private' AND p.proname IN ('is_approved_operator','is_approved_admin')) ORDER BY 1,2;

COMMIT;
