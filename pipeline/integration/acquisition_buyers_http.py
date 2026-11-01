"""Mounted buyer API with signed JWTs and real local PostgREST, no hosted calls."""
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
import httpx


def verify_buyers_http(db, request, token, admin, other, workspace):
    from tools.acquisition_store import AcquisitionStore, acquisition_store
    from web.api.acquisition_api import router
    buyer='af160000-0000-4000-8000-000000000001'
    first='af160000-0000-4000-8000-000000000002'
    second='af160000-0000-4000-8000-000000000003'
    details=dict(first_name='Synthetic',last_name='Buyer',company=None,email='synthetic@example.test',phone=None,
        target_zips=['75201'],property_types=['SFR'],strategies=['fix_flip'],min_price_cents=None,
        max_price_cents=35000000,max_repairs_cents=None,close_speed_days=None,active=True,
        source_note='Self-reported synthetic buyer preferences awaiting independent review.')
    body=dict(id=first,buyer_id=buyer,expected_revision=0,details=details)
    lost=[True]
    class Store(AcquisitionStore):
        async def request(self,method,path,**kwargs):
            result=await super().request(method,path,**kwargs)
            if path=='rpc/record_acquisition_buyer' and lost[0]:
                lost[0]=False
                raise HTTPException(503,'Synthetic response lost after commit')
            return result
    def gateway(req):
        if req.url.host!='localhost' or req.method not in ('GET','POST'):
            raise AssertionError('Unexpected buyer gateway destination or method')
        path=req.url.path+('?' + req.url.query.decode() if req.url.query else '')
        jwt=req.headers.get('authorization','').removeprefix('Bearer ') or None
        status,data=request(path,jwt,json.loads(req.content) if req.method=='POST' else None)
        return httpx.Response(status,content=json.dumps(data),headers={'Content-Type':'application/json'})
    async def store(incoming:Request):
        async with httpx.AsyncClient(base_url='http://localhost/',trust_env=False,
                transport=httpx.MockTransport(gateway),headers={'Authorization':incoming.headers.get('authorization','')}) as client:
            yield Store(client)
    app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=store
    path=f'/api/acquisition/workspaces/{workspace}/buyers'
    headers={'Authorization':'Bearer '+token()}
    foreign={'Authorization':'Bearer '+token(other)}
    with TestClient(app) as client:
        for auth in ({},foreign,{'Authorization':'Bearer '+token(role='service_role')}):
            for response in (client.get(path,headers=auth),client.post(path,headers=auth,json=body)):
                assert response.status_code in (401,403),response.text
        response=client.post(path,headers=headers,json=body)
        assert response.status_code==503 and 'X-Acquisition-Buyer-Rejected' not in response.headers
        assert db.query('SELECT acquisition_revision FROM buyers WHERE id=%s',[buyer])[0]['acquisition_revision']==1
        response=client.post(path,headers=headers,json=body)
        assert response.status_code==200,response.text
        receipt=response.json()
        assert receipt==dict(request_id=first,workspace_id=workspace,buyer_id=buyer,revision=1,details=details,
            duplicate=True,profile_recorded=True,buyer_verified=False,contact_authorized=False,execution_authorized=False)
        assert response.headers['Cache-Control']=='no-store'
        changed=body|{'id':second,'expected_revision':1,'details':details|{'max_price_cents':None,'active':False}}
        response=client.post(path,headers=headers,json=changed)
        assert response.status_code==200 and response.json()['revision']==2,response.text
        stale=client.post(path,headers=headers,json=body|{'id':'af160000-0000-4000-8000-000000000004'})
        assert stale.status_code==409 and stale.headers['X-Acquisition-Buyer-Rejected']=='true',stale.text
        conflict=client.post(path,headers=headers,json=body|{'details':details|{'first_name':'Changed'}})
        assert conflict.status_code==409 and conflict.headers['X-Acquisition-Buyer-Rejected']=='true',conflict.text
        replay=client.post(path,headers=headers,json=body)
        assert replay.status_code==200 and replay.json()==receipt,replay.text
        listing=client.get(path+'?limit=1',headers=headers)
        assert listing.status_code==200,listing.text
        page=listing.json()
        assert page['workspace_id']==workspace and len(page['items'])==1 and page['next_cursor'] is None
        assert set(page['items'][0])=={'buyer_id','revision','first_name','last_name','company','active','buyer_verified'}
        assert page['items'][0]['revision']==2 and not page['items'][0]['active']
        assert client.get(path+'?limit=1&after='+buyer,headers=headers).json()['items']==[]
        profile=client.get(path+'/'+buyer,headers=headers)
        assert profile.status_code==200 and profile.json()['details']==changed['details'] and profile.json()['revision']==2,profile.text
        assert client.get(path+'/'+buyer,headers=foreign).status_code==403
        missing=client.get(path+'/af160000-0000-4000-8000-000000000099',headers=headers)
        assert missing.status_code==404,missing.text
        assert request('/buyers?id=eq.'+buyer+'&select=id',token())==(200,[])
        assert request('/buyer_leaderboard?id=eq.'+buyer,token(role='service_role'))==(200,[])
        db.query('UPDATE private.acquisition_activation SET enabled=false')
        try:
            assert client.get(path,headers=headers).json()['can_save'] is False
            assert client.post(path,headers=headers,json=body).json()==receipt
            denied=client.post(path,headers=headers,json=changed|{'id':'af160000-0000-4000-8000-000000000005','expected_revision':2})
            assert denied.status_code==409 and denied.headers['X-Acquisition-Buyer-Rejected']=='true',denied.text
        finally:db.query('UPDATE private.acquisition_activation SET enabled=true')
        db.query("UPDATE workspace_memberships SET status='revoked' WHERE workspace_id=%s AND user_id=%s",[workspace,admin])
        try:
            assert client.get(path,headers=headers).status_code==403
            assert client.post(path,headers=headers,json=body).status_code==403
        finally:db.query("UPDATE workspace_memberships SET status='active' WHERE workspace_id=%s AND user_id=%s",[workspace,admin])
        assert db.query('SELECT count(*) AS n FROM private.acquisition_buyer_versions WHERE buyer_id=%s',[buyer])[0]['n']==2
        assert db.query("SELECT count(*) AS n FROM audit_logs WHERE entity_type='acquisition_buyer' AND workspace_id=%s",[workspace])[0]['n']==2
    return ['buyer mounted HTTP signed tenant/anonymous/service isolation','buyer HTTP lost-after-commit exact recovery without duplicate audit',
        'buyer HTTP immutable historical replay after later revision','buyer HTTP stale and conflicting requests rejected',
        'buyer HTTP bounded private-contact-free list and current profile','buyer HTTP legacy raw and service view containment',
        'buyer HTTP paused reads and historical recovery without new writes','buyer HTTP membership suspension blocks reads and replay']
