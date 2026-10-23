"""Buyer reads against restored production schema with a deliberately low row cap."""
import json
from unittest.mock import patch
from uuid import UUID

from tests.local_journey_db import Database
from web.api import buyers_api as api


def verify(db):
    # Namespaced deterministic UUIDs place the best buyer beyond the first 1,000 rows.
    ids = [str(UUID(int=(0xBA << 120) + n)) for n in range(1003)]
    db.query("""INSERT INTO public.buyers (id,first_name,last_name,active,target_zips,min_price,max_price,property_types,ibie_score)
        SELECT value::uuid,'Synthetic buyer',ordinality::text,true,ARRAY['00000'],1,2,ARRAY['SFR'],0
        FROM jsonb_array_elements_text(%s::jsonb) WITH ORDINALITY AS t(value,ordinality)""", [json.dumps(ids)])
    best = ids[-1]
    db.query("UPDATE public.buyers SET target_zips=ARRAY['75201'],min_price=100000,max_price=200000,ibie_score=100 WHERE id=%s", [best])
    db.query("""INSERT INTO public.buyer_transactions (buyer_id,property_address,purchase_date)
        SELECT %s::uuid,'Synthetic purchase '||n,current_date-n FROM generate_series(1,1003) AS n""", [best])
    db.response_cap = 200
    db.query('SET ROLE service_role')
    with patch.object(api, '_get_supabase', return_value=db):
        history = api.get_buyer_transactions(best)
        assert history['buyer_id'] == best and history['total'] == 1003
        assert len({row['id'] for row in history['transactions']}) == 1003
        assert all(row['buyer_id'] == best for row in history['transactions'])
        matches = api.match_deal_to_buyers(api.MatchRequest(zip_code='75201',buyer_price=150000,property_type='SFR',limit=1))
        assert matches['matches'][0]['buyer_id'] == best, matches
        db.query('UPDATE public.buyers SET active=false WHERE id=%s', [best])
        remaining = api.match_deal_to_buyers(api.MatchRequest(zip_code='75201',buyer_price=150000,property_type='SFR',limit=1))['matches']
        assert all(row['buyer_id'] != best for row in remaining)
    db.query('RESET ROLE')
    print(json.dumps({'buyer_reads':'passed','synthetic_buyers':1003,'purchase_history_rows':1003,
        'response_cap':200,'best_buyer_beyond_first_1000':'matched','inactive_buyer':'excluded','provider_calls':0}),flush=True)


if __name__ == '__main__':
    db = Database()
    try: verify(db)
    finally: db.connection.close()
