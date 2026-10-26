import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { ScenarioEditor } from '../src/pages/AcquisitionUnderwriting';
const mock=vi.hoisted(()=>({fetch:vi.fn(),hash:'a'.repeat(64),classification:'qualified',fail:false,current:true,bad:false}));
vi.mock('@/lib/api',()=>({apiFetch:mock.fetch,ApiError:class extends Error{status=409;}}));
const assessment={classification:'qualified',reason_codes:[],missing_fields:[],policy_version:'intake-qualification-v1',canonical_county:'Dallas',canonical_state:'TX',identity_link_current:true,ownership_verified:false,outreach_authorized:false,binding_offer:false,contact_permission_granted:false};
beforeEach(()=>{mock.hash='a'.repeat(64);mock.classification='qualified';mock.fail=false;mock.current=true;mock.bad=false;mock.fetch.mockReset();mock.fetch.mockImplementation(async(path:string,init?:RequestInit)=>{
  if(init?.method==='POST'){
    if(mock.fail){mock.fail=false;throw new Error('reply lost');}
    const body=JSON.parse(String(init.body));return {json:async()=>({binding_offer:false,analysis:{id:body.id,acquisition_revision:1,acquisition_status:'incomplete',acquisition_strategy:'fix_and_flip',acquisition_outputs:null},calculation:{status:'incomplete'},intake_context:{analysis_id:body.id,intake_id:mock.bad?'different':'intake',assessment_id:body.id,has_intake:true,qualification_current:mock.current}})};
  }
  return {json:async()=>({assessment:{...assessment,classification:mock.classification},evidence_hash:mock.hash,sequence:0,latest_assessment:null,assessment_current:false})};
});});
function open(){const saved=vi.fn(),pending=vi.fn();render(<ScenarioEditor path="/canonical/underwriting" intake={{path:'/intakes/intake',id:'intake',evidenceHash:'a'.repeat(64)}} onSaved={saved} onPending={pending}/>);fireEvent.click(screen.getByText('New underwriting scenario'));return {saved,pending};}
it('uses dedicated intake reservation with fresh evidence and no client target override',async()=>{
  const {saved,pending}=open();fireEvent.click(screen.getByRole('button',{name:'Save scenario'}));await screen.findByText(/Saved revision/);
  const request=mock.fetch.mock.calls.find(c=>c[1]?.method==='POST')!;expect(request[0]).toBe('/intakes/intake/underwriting/scenarios');
  expect(Object.keys(JSON.parse(request[1].body)).sort()).toEqual(['evidence_hash','id','inputs']);expect(saved).toHaveBeenCalledWith(expect.objectContaining({acquisition_status:'incomplete'}),true);
  await waitFor(()=>expect(pending).toHaveBeenLastCalledWith(false));
});
it('rejects changed evidence before reserving anything',async()=>{
  open();mock.hash='b'.repeat(64);fireEvent.click(screen.getByRole('button',{name:'Save scenario'}));await screen.findByText(/Qualification changed/);
  expect(mock.fetch.mock.calls.filter(c=>c[1]?.method==='POST')).toHaveLength(0);
});
it('rejects no-longer-qualified intake even if a malformed service returns the same hash',async()=>{
  open();mock.classification='duplicate';fireEvent.click(screen.getByRole('button',{name:'Save scenario'}));await screen.findByText(/Qualification changed/);
  expect(mock.fetch.mock.calls.filter(c=>c[1]?.method==='POST')).toHaveLength(0);
});
it('reconciles the exact request after a lost reply even when evidence changed',async()=>{
  const {saved,pending}=open();mock.fail=true;fireEvent.click(screen.getByRole('button',{name:'Save scenario'}));await screen.findByText(/Save outcome unconfirmed/);
  await waitFor(()=>expect(pending).toHaveBeenLastCalledWith(true));expect(screen.getByLabelText('Strategy')).toBeDisabled();
  mock.hash='c'.repeat(64);mock.current=false;fireEvent.click(screen.getByRole('button',{name:'Retry same scenario'}));await screen.findByText(/Saved revision/);
  const posts=mock.fetch.mock.calls.filter(c=>c[1]?.method==='POST');expect(posts[0][1].body).toBe(posts[1][1].body);expect(saved).toHaveBeenLastCalledWith(expect.anything(),false);
});
it('keeps a mismatched provenance response unresolved instead of accepting success',async()=>{
  const {saved,pending}=open();mock.bad=true;fireEvent.click(screen.getByRole('button',{name:'Save scenario'}));await screen.findByText(/Save outcome unconfirmed/);
  expect(saved).not.toHaveBeenCalled();await waitFor(()=>expect(pending).toHaveBeenLastCalledWith(true));
});
