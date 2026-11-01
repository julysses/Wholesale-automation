"""Real bounded buyer read projections, including private fields and tenant isolation."""
import json
from pathlib import Path
from acquisition_buyer_catalog_inventory import main
from acquisition_buyer_profile_tests import probe as profile_probe,PROFILE,USER,WS,WS2,BUYER,LEGACY
from schemas.acquisition_buyers import AcquisitionBuyerIndex,AcquisitionBuyerProfile


def probe(db):
    profile_probe(db)
    db.query('UPDATE private.acquisition_activation SET enabled=true')
    db.query("UPDATE workspace_memberships SET status='active' WHERE workspace_id=%s AND user_id=%s",[WS,USER])
    def rpc(name,args,role='authenticated',aal='aal2',fails=False):
        db.query('SET ROLE '+role)
        try:
            db.query("SELECT set_config('request.jwt.claims',%s,false)",[json.dumps(dict(sub=USER,role=role,session_id=USER,aal=aal))])
            try:result=db.query('SELECT public.'+name+'('+','.join(['%s']*len(args))+') AS value',args)[0]['value']
            except Exception:
                if fails:return
                raise
            if fails:raise AssertionError('Expected buyer discovery rejection')
            return result
        finally:
            db.query('RESET ROLE');db.query("SELECT set_config('request.jwt.claims','{}',false)")
    for role in ('anon','service_role'):
        rpc('acquisition_buyer_index',[WS,None,25],role=role,fails=True)
        rpc('acquisition_buyer_profile',[WS,PROFILE],role=role,fails=True)
    rpc('acquisition_buyer_index',[WS,None,25],aal='aal1',fails=True)
    rpc('acquisition_buyer_index',[WS2,None,25],fails=True)
    for limit in (0,51,None):rpc('acquisition_buyer_index',[WS,None,limit],fails=True)
    db.query("UPDATE profiles SET role='user' WHERE id=%s",[USER])
    for role in ('operator','acquisition_caller','agency_manager'):
        db.query('UPDATE workspace_memberships SET role=%s WHERE workspace_id=%s AND user_id=%s',[role,WS,USER])
        rpc('acquisition_buyer_profile',[WS,PROFILE],fails=True)
    db.query("UPDATE workspace_memberships SET role='owner' WHERE workspace_id=%s AND user_id=%s",[WS,USER])
    db.query("UPDATE profiles SET role='admin' WHERE id=%s",[USER])
    profile=AcquisitionBuyerProfile.model_validate(rpc('acquisition_buyer_profile',[WS,PROFILE]))
    assert profile.revision==3 and profile.can_save and profile.details.max_price_cents==30000000
    assert rpc('acquisition_buyer_profile',[WS,LEGACY]) is None
    assert rpc('acquisition_buyer_profile',[WS,BUYER]) is None
    for n in range(1,4):
        identity=f'af152000-0000-4000-8000-{n:012d}'
        rpc('record_acquisition_buyer',[identity,WS,identity,0,json.dumps(profile.details.model_dump(mode='json'))])
    before=db.query('SELECT count(*) AS n FROM private.acquisition_buyer_versions')
    cursor=None;seen=[]
    while True:
        raw=rpc('acquisition_buyer_index',[WS,cursor,2]);page=AcquisitionBuyerIndex.model_validate(raw)
        assert len(page.items)<=2 and page.workspace_id==profile.workspace_id
        for item in raw['items']:assert set(item)=={'buyer_id','revision','first_name','last_name','company','active','buyer_verified'}
        seen.extend(str(item.buyer_id) for item in page.items)
        if page.next_cursor is None:break
        cursor=str(page.next_cursor)
    assert len(seen)==len(set(seen))==4
    assert PROFILE in seen and BUYER not in seen and LEGACY not in seen
    assert before==db.query('SELECT count(*) AS n FROM private.acquisition_buyer_versions')
    db.query("INSERT INTO workspace_memberships(workspace_id,user_id,role) VALUES(%s,%s,'owner')",[WS2,USER])
    assert rpc('acquisition_buyer_index',[WS2,None,25])['items']==[]
    assert rpc('acquisition_buyer_profile',[WS2,PROFILE]) is None
    db.query('UPDATE private.acquisition_activation SET enabled=false')
    assert not rpc('acquisition_buyer_profile',[WS,PROFILE])['can_save']
    assert not rpc('acquisition_buyer_index',[WS,None,25])['can_save']
    db.query("UPDATE auth.sessions SET not_after=clock_timestamp()-interval '1 second' WHERE id=%s",[USER])
    rpc('acquisition_buyer_index',[WS,None,25],fails=True)
    result={'scope':'Disposable full118 catalog; actual authenticated read RPCs and typed projections; mounted API/UI still pending',
            'checks':['owner MFA/session/role and service denials','bounded pagination without duplicates','list omits contact details',
                      'profile exact latest revision','legacy and unversioned scoped rows absent','cross-workspace identity rejected even for shared owner',
                      'paused historical reads without save permission','read operations append no versions'],
            'production_changed':False}
    Path('docs/acquisition-automation/evidence/2026-11-01-buyer-discovery-focused-result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


class BuyerDiscoveryCases:
    def test_acquisition_buyer_profile_and_discovery(self):
        import psycopg2
        from rehearse_acquisition_baseline import DisposableDatabase
        db = object.__new__(DisposableDatabase)
        db.connection = psycopg2.connect(
            host=self.socket, dbname=self.database_name,
            user='test_admin', connect_timeout=5,
        )
        db.connection.autocommit = True
        try:
            probe(db)
        finally:
            db.connection.close()


if __name__ == '__main__':
    main(probe)
