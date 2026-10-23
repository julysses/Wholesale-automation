import fs from 'node:fs';
import {setup,id,rpc} from './scoring-fixture.mjs';
export async function fixture(t){
 const f=await setup(t);
 await f.db.exec(`CREATE TABLE public.land_leads(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),lead_id uuid,source text,owner_name text NOT NULL,property_address text,city text,state text,zip_code text,county text,apn text,status text,assigned_to uuid,sms_sequence_active boolean,offer_price numeric,mao numeric);
 INSERT INTO public.profiles VALUES('${id(10)}','admin','approved'),('${id(11)}','user','approved'),('${id(12)}','user','approved');
 UPDATE wholesale_ingest.properties SET city='Dallas';UPDATE wholesale_ingest.settings SET score_threshold=30;`);
 await f.db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261020163212_integration_list_lot_handoff.sql',import.meta.url),'utf8'));
 await f.db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261020163214_integration_list_lot_receiving_evidence.sql',import.meta.url),'utf8'));
 await f.db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261020163215_integration_list_lot_worker.sql',import.meta.url),'utf8'));
 await f.db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261020163217_integration_list_lot_reconciliation.sql',import.meta.url),'utf8'));
 await f.db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261020163218_integration_list_lot_missing_property.sql',import.meta.url),'utf8'));
 const hash=(await rpc(f.db,'list_scoring_input',[id(1)])).input_hash;
 const review=()=>rpc(f.db,'review_list_lot',[id(20),id(10),id(1),hash,true,'https://example.invalid/official-lot','Reviewed exact parcel classification']);
 const score=async()=>{const s=await rpc(f.db,'list_scoring_input',[id(1)]);return rpc(f.db,'save_list_score',[id(5),id(1),s.input_hash,'claude-fixture','daily-list-score-v1','msg-fixture',JSON.stringify(f.result)]);};
 const handoff=(event=id(21))=>rpc(f.db,'handoff_list_lot',[event,id(10),id(5),id(11)]);
 return {...f,hash,review,score,handoff};
}
