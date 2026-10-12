import {fireEvent,render,screen} from '@testing-library/react';
import {beforeEach,expect,it,vi} from 'vitest';
const mocks=vi.hoisted(()=>({fetch:vi.fn()}));
vi.mock('@/lib/api',()=>({apiFetch:mocks.fetch,ApiError:class extends Error{}}));
import {OfferHistory} from '@/components/offers/OfferHistory';
import {readOfferHistory} from '@/lib/offerReview';
const lead='00000000-0000-4000-8000-000000000001';
const actor='00000000-0000-4000-8000-000000000002';
const event=(version:number)=>({id:`00000000-0000-4000-8000-${String(version+100).padStart(12,'0')}`,lead_id:lead,operator_id:actor,expected_version:version,action:'revoke',revision_id:lead,terms:null,created_at:'2026-10-12T20:00:00Z'});
const response=(events:ReturnType<typeof event>[],next_before:number|null=null)=>({json:async()=>({lead_id:lead,events,next_before})});
beforeEach(()=>vi.resetAllMocks());
it('shows revoking actor and loads older decisions without losing the first page',async()=>{
 mocks.fetch.mockResolvedValueOnce(response(Array.from({length:50},(_,i)=>event(50-i)),1)).mockResolvedValueOnce(response([event(0)]));
 render(<OfferHistory lead={lead}/>);
 expect(await screen.findByText('Version 51: Approval revoked')).toBeTruthy();
 expect(screen.getAllByText(new RegExp(actor))).toHaveLength(50);
 fireEvent.click(screen.getByRole('button',{name:'Load older decisions'}));
 expect(await screen.findByText('Version 1: Approval revoked')).toBeTruthy();
 expect(screen.getByText('Version 51: Approval revoked')).toBeTruthy();
 expect(mocks.fetch).toHaveBeenLastCalledWith(`/api/operations/offers/${lead}/history?before=1`);
 expect(screen.queryByRole('button',{name:'Load older decisions'})).toBeNull();
});
it('reports failures rather than showing an empty audit record and retries',async()=>{
 mocks.fetch.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(response([]));
 render(<OfferHistory lead={lead}/>);
 await screen.findByRole('alert');expect(screen.queryByText('No decisions recorded.')).toBeNull();
 fireEvent.click(screen.getByRole('button',{name:'Retry history'}));
 await screen.findByText('No decisions recorded.');
});
it('rejects another lead or a non-advancing page',async()=>{
 mocks.fetch.mockResolvedValueOnce(response([{...event(2),lead_id:actor}]));
 await expect(readOfferHistory(lead)).rejects.toThrow('history order');
 mocks.fetch.mockResolvedValueOnce(response([event(3)]));
 await expect(readOfferHistory(lead,3)).rejects.toThrow('history order');
});
