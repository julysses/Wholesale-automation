import fs from 'node:fs';
import {database} from './helpers.mjs';
export const id=n=>`00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;
export const rpc=async(db,name,args)=>(await db.query(`select public.${name}(${args.map((_,i)=>'$'+(i+1)).join(',')}) v`,args)).rows[0].v;
export async function setup(t){
 const db=await database();t.after(()=>db.close());
 await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261012231220_list_scoring_receipts.sql',import.meta.url),'utf8'));
 await db.exec(`INSERT INTO public.leads(id,property_address) VALUES('${id(1)}','SYNTHETIC SCORING');
 INSERT INTO wholesale_ingest.properties(id,state,county,address_std,lead_id) VALUES('${id(2)}','TX','Dallas','SYNTHETIC SCORING','${id(1)}');
 INSERT INTO wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,status,status_reason,manifest_hash,expected_batches)
 SELECT '${id(3)}',id,current_date,now(),'success','synthetic',repeat('a',64),1 FROM wholesale_ingest.sources WHERE source_key='tx-dallas-pre_foreclosure';
 INSERT INTO wholesale_ingest.distress_signals(id,property_id,source_id,source_record_id,list_type,filed_date,source_url,first_run_id,last_run_id)
 SELECT '${id(4)}','${id(2)}',source_id,'synthetic','pre_foreclosure',(now() AT TIME ZONE 'America/Chicago')::date,'https://example.invalid/fixture','${id(3)}','${id(3)}' FROM wholesale_ingest.ingest_runs WHERE id='${id(3)}';`);
 const snapshot=await rpc(db,'list_scoring_input',[id(1)]);
 const part=(points,ids=[])=>({points,reason:'Synthetic evidence interpretation',evidence_ids:ids});
 const result={components:{distress_stack:part(7,[id(4)]),need_to_sell:part(15,[id(4)]),equity:part(0),contactability:part(0),recency:part(10,[id(4)])},needs_to_sell:'inferred'};
 const save=()=>rpc(db,'save_list_score',[id(5),id(1),snapshot.input_hash,'claude-fixture','daily-list-score-v1','msg-fixture',JSON.stringify(result)]);
 return {db,result,save,snapshot};
}
