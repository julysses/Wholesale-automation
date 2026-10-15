import fs from 'node:fs';
import {fixture as lotFixture} from './lot-fixture.mjs';
import {id,rpc} from './scoring-fixture.mjs';
export const payload=()=>({direct_comp_details:[],avg_house_arv:null,house_comp_count:null,tav:0,tav_source:'manual',tav_assessment_date:null,comp_notes:'Synthetic evidence'});
export async function fixture(t){
 const {db}=await lotFixture(t);
 const original=fs.readFileSync(new URL('../../frontend/supabase/migrations/007_land_wholesaling.sql',import.meta.url),'utf8');
 const table=original.slice(original.indexOf('CREATE TABLE IF NOT EXISTS land_comps ('),original.indexOf('ALTER TABLE land_comps ENABLE'));
 await db.exec(table.replace('IF NOT EXISTS land_comps','public.land_comps').replaceAll('uuid_generate_v4()','gen_random_uuid()'));
 await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261013031711_land_valuation_receipts.sql',import.meta.url),'utf8'));
 await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261013033643_preserve_valuation_radius.sql',import.meta.url),'utf8'));
 await db.exec(`INSERT INTO public.land_leads(id,property_address,city,state,county,owner_name,status,offer_price,mao) VALUES('${id(70)}','SYNTHETIC VALUATION','Dallas','TX','Dallas',NULL,'new',12345,23456)`);
 const read=()=>rpc(db,'read_land_valuation',[id(70),id(11)]);
 const save=(hash,p=payload(),event=id(71))=>rpc(db,'save_land_valuation',[event,id(11),id(70),hash,JSON.stringify(p)]);
 return {db,read,save};
}
