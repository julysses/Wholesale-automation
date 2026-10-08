import { beforeEach, expect, it, vi } from 'vitest';
const mocks=vi.hoisted(()=>({api:vi.fn()}));
vi.mock('@/lib/api',async importOriginal=>({...await importOriginal<typeof import('@/lib/api')>(),apiFetch:mocks.api}));
import {ApiError} from '@/lib/api';
import {createPipelineDeal,pendingDeal,updatePipelineDeal} from '@/lib/dealWrites';
beforeEach(()=>{sessionStorage.clear();mocks.api.mockReset();});
const deal={lead_id:'lead-qa',deal_name:'Internal QA',stage:'offer_made'};
it('recovers an uncertain creation with the same immutable reference after reload',async()=>{
 mocks.api.mockRejectedValueOnce(new Error('Acknowledgement lost'));
 await expect(createPipelineDeal(deal,vi.fn())).rejects.toThrow('Acknowledgement lost');
 const pending=pendingDeal();expect(pending?.deal).toEqual(deal);
 mocks.api.mockImplementation(async(_path,init)=>({json:async()=>({id:JSON.parse(init.body).request_id,updated_at:'2026-10-08T12:00:00Z'})}));
 await createPipelineDeal(pending!.deal,vi.fn());
 expect(mocks.api.mock.calls[0][1].body).toBe(mocks.api.mock.calls[1][1].body);expect(pendingDeal()).toBeNull();
});
it('refuses another lead or changed draft until the pending creation is recovered',async()=>{
 mocks.api.mockRejectedValue(new Error('Unknown'));
 await expect(createPipelineDeal(deal,vi.fn())).rejects.toThrow();
 await expect(createPipelineDeal({...deal,lead_id:'other'},vi.fn())).rejects.toThrow('unconfirmed deal create');
 expect(mocks.api).toHaveBeenCalledTimes(1);
});
it('bad acknowledgement remains recoverable rather than clearing the durable reference',async()=>{
 mocks.api.mockResolvedValue({json:async()=>({id:'different',updated_at:'2026-10-08T12:00:00Z'})});
 await expect(createPipelineDeal(deal,vi.fn())).rejects.toThrow('unconfirmed');expect(pendingDeal()).not.toBeNull();
});
it('updates carry the observed version and date null without creating another deal',async()=>{
 mocks.api.mockResolvedValue({json:async()=>({id:'deal-qa',updated_at:'2026-10-08T12:01:00Z'})});
 await updatePipelineDeal('deal-qa','2026-10-08T12:00:00Z',{inspection_deadline:null});
 expect(JSON.parse(mocks.api.mock.calls[0][1].body)).toEqual({expected_updated_at:'2026-10-08T12:00:00Z',updates:{inspection_deadline:null}});
});
it('allows correcting a definitely rejected create while preserving an unknown conflict',async()=>{
 mocks.api.mockRejectedValueOnce(new ApiError('Invalid evidence',422));
 await expect(createPipelineDeal(deal,vi.fn())).rejects.toThrow('Invalid evidence');expect(pendingDeal()).toBeNull();
 mocks.api.mockRejectedValueOnce(new ApiError('Already active',409,true));
 await expect(createPipelineDeal(deal,vi.fn())).rejects.toThrow('Already active');expect(pendingDeal()).toBeNull();
 mocks.api.mockRejectedValueOnce(new ApiError('Reference conflict',409));
 await expect(createPipelineDeal(deal,vi.fn())).rejects.toThrow('Reference conflict');expect(pendingDeal()).not.toBeNull();
});
