import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { PropertySources } from '../src/components/acquisition/PropertySources';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), page: {} as Record<string, unknown> }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch }));
const w='10000000-0000-4000-8000-000000000001',lead='20000000-0000-4000-8000-000000000001',property='30000000-0000-4000-8000-000000000001',source='40000000-0000-4000-8000-000000000001',review='50000000-0000-4000-8000-000000000001',campaign='60000000-0000-4000-8000-000000000001';
const touch={source_type:'facebook_native_form',inbound_revision:null,inbound_event_id:null,integration_id:w,external_lead_id:'123',source_id:source,original_lead_id:source,association:'reviewed_repeat_inquiry',identity_review_id:review,attribution_status:'campaign_review_not_current',attribution_current:false,current_campaign_id:null,captured_attribution:{id:review,campaign_id:campaign,link_review_id:review,created_at:'2026-10-26T12:00:00Z'}};
beforeEach(()=>{mock.fetch.mockReset();mock.page={workspace_id:w,canonical_lead_id:lead,property_id:property,items:[touch],next_after:null,scanned_count:1,excluded_count:0,checked_at:'2026-10-26T12:00:00Z',count_scope:'bounded_candidate_page',totals_available:false,ownership_verified:false,contact_permission_granted:false,execution_authorized:false};mock.fetch.mockImplementation(async()=>({json:async()=>({...mock.page})}));});
function view(){render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><PropertySources userId="user" workspace={w} lead={lead} property={property}/></QueryClientProvider>);}
function open(){fireEvent.click(screen.getByRole('button',{name:'View property inquiry sources'}));}
it('loads on request and distinguishes historical attribution',async()=>{view();expect(mock.fetch).not.toHaveBeenCalled();open();await screen.findByText('Reviewed repeat inquiry');expect(screen.getByText(`Historical attribution: ${campaign}`)).toBeInTheDocument();expect(screen.getByText(`Original lead: ${source}`)).toBeInTheDocument();});
it('continues an empty candidate page and refreshes from first page',async()=>{mock.page={...mock.page,items:[],scanned_count:20,excluded_count:20,next_after:source};view();open();await screen.findByText('No eligible inquiry touches on this page.');mock.page={...mock.page,scanned_count:0,excluded_count:0,next_after:null};fireEvent.click(screen.getByRole('button',{name:'More property sources'}));await waitFor(()=>expect(mock.fetch).toHaveBeenCalledTimes(2));expect(mock.fetch.mock.calls[1][0]).toContain(`after=${source}`);await waitFor(()=>expect(screen.getByRole('button',{name:'Refresh from first source page'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'Refresh from first source page'}));await waitFor(()=>expect(mock.fetch).toHaveBeenCalledTimes(3));expect(mock.fetch.mock.calls[2][0]).not.toContain('after=');});
it.each([{workspace_id:source},{property_id:source},{canonical_lead_id:source},{execution_authorized:true},{scanned_count:0},{items:[{...touch,attribution_current:true}]},{items:[touch,touch],scanned_count:2},{next_after:source},{items:[{...touch,association:'original_lead'}]}])('rejects invalid response %j',async patch=>{mock.page={...mock.page,...patch};view();open();await screen.findByRole('alert');expect(screen.queryByText('Reviewed repeat inquiry')).not.toBeInTheDocument();expect(screen.getByRole('button',{name:'More property sources'})).toBeDisabled();});
it('hides previous evidence after denied refresh',async()=>{view();open();await screen.findByText('Reviewed repeat inquiry');mock.fetch.mockRejectedValue(new Error('403'));fireEvent.click(screen.getByRole('button',{name:'Refresh from first source page'}));await screen.findByRole('alert');expect(screen.queryByText('Reviewed repeat inquiry')).not.toBeInTheDocument();});
it('shows current campaign only with matching captured attribution',async()=>{mock.page.items=[{...touch,attribution_current:true,attribution_status:'current_captured_attribution',current_campaign_id:campaign}];view();open();await screen.findByText(`Current campaign: ${campaign}`);expect(screen.queryByText(/Historical attribution:/)).not.toBeInTheDocument();});

it('labels inbound revisions without claiming separate leads or campaign attribution',async()=>{
  mock.page.items=[{...touch,source_type:'retell_inbound',inbound_revision:2,inbound_event_id:review,external_lead_id:'call_test',captured_attribution:null,attribution_status:'campaign_evidence_unavailable'}];
  view();open();await screen.findByText('Inbound call evidence · revision 2');
  expect(screen.getByText(/Call: call_test/)).toBeInTheDocument();
  expect(screen.getByText(/Multiple revisions of one call belong to the same lead/)).toBeInTheDocument();
  expect(screen.queryByText(/Historical attribution:/)).not.toBeInTheDocument();
});
it('rejects malformed inbound revision metadata',async()=>{
  mock.page.items=[{...touch,source_type:'retell_inbound',inbound_revision:0,inbound_event_id:review,external_lead_id:'call_test',captured_attribution:null}];
  view();open();await screen.findByRole('alert');
});
