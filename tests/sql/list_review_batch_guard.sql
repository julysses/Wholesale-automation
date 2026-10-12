-- Isolated rehearsal only; every fixture and CRM write is rolled back.
BEGIN;
DO $$
<<list_review_batch_guard>>
DECLARE owner_id uuid; run_id uuid:=gen_random_uuid(); src_id uuid; result jsonb;
BEGIN
 SELECT id INTO owner_id FROM public.profiles WHERE role='admin' AND status='approved' LIMIT 1;
 IF owner_id IS NULL THEN RAISE EXCEPTION 'Approved rehearsal administrator fixture required'; END IF;
 SELECT id INTO src_id FROM wholesale_ingest.sources WHERE source_key='tx-dallas-pre_foreclosure';
 INSERT INTO wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,status,status_reason,manifest_hash,expected_batches)
 VALUES(run_id,src_id,current_date,now(),'success','synthetic rollback test',repeat('a',64),2);
 INSERT INTO wholesale_ingest.raw_payloads(run_id,batch_index,payload_hash,records_hash,payload,records_in)
 VALUES(run_id,0,repeat('b',64),repeat('c',64),'{}',1);
 INSERT INTO wholesale_ingest.records(run_id,batch_index,ordinal,source_record_id,record,review_reason)
 VALUES(run_id,0,0,'synthetic-'||run_id,jsonb_build_object('property_address','Synthetic '||run_id,'city','Dallas','state','TX','zip','75201','filed_date',current_date,'source_url','https://www.dallascounty.org/synthetic'),'verify_county_property_evidence');
 BEGIN
  PERFORM public.resolve_list_record(run_id,0,0,owner_id,'Dallas','https://www.dallascad.org/synthetic');
  RAISE EXCEPTION 'Expected incomplete-batch rejection';
 EXCEPTION WHEN raise_exception THEN
  IF SQLERRM<>'Complete unexpired batch set required before property review' THEN RAISE; END IF;
 END;
 ASSERT NOT EXISTS(SELECT 1 FROM wholesale_ingest.review_events WHERE review_events.run_id=list_review_batch_guard.run_id), 'Unexpected review write';
END $$;
ROLLBACK;
