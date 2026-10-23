import { beforeEach, expect, it, vi } from 'vitest';
const state=vi.hoisted(() => ({ api:vi.fn(), actor:'00000000-0000-4000-8000-000000000001' }));
vi.mock('@/lib/api',()=>({apiFetch:state.api}));
vi.mock('@/lib/supabase',()=>({supabase:{auth:{getSession:async()=>({data:{session:{user:{id:state.actor}}},error:null})}}}));
import { pendingBuyerChange, recoverBuyerChange, saveBuyerChange } from '@/lib/buyerChanges';
const row={id:'00000000-0000-4000-8000-000000000002',first_name:'Synthetic',last_name:'Buyer',notes:'Before'};
const updates={first_name:'Synthetic',last_name:'Buyer',notes:'After'};
const response=(value:unknown)=>new Response(JSON.stringify(value));
const result=(id:string,kind='update')=>({id,state:kind==='update'?'updated':'deleted',kind,buyer_id:row.id,buyer:{...row,...updates},current_exists:kind==='update',transaction_count:0});
beforeEach(()=>{
 vi.restoreAllMocks();state.api.mockReset();sessionStorage.clear();state.actor='00000000-0000-4000-8000-000000000001';
 state.api.mockImplementation(async (_path,init)=>{const value=JSON.parse(init.body);return response(result(value.request_id,value.kind));});
});
it('persists the original expected record before writing and binds the request actor',async()=>{
 state.api.mockImplementationOnce(async (_path,init,actor)=>{
  const value=JSON.parse(init.body);expect((await pendingBuyerChange())?.request_id).toBe(value.request_id);
  expect(value.expected).toEqual(row);expect(actor).toBe(state.actor);return response(result(value.request_id));
 });
 expect((await saveBuyerChange('update',row,updates)).state).toBe('updated');expect(await pendingBuyerChange()).toBeNull();
});
it('recovers a lost response with exactly the same edit and rejects changed inputs',async()=>{
 state.api.mockRejectedValueOnce(new Error('Synthetic response loss'));
 await expect(saveBuyerChange('update',row,updates)).rejects.toThrow('response loss');
 const first=state.api.mock.calls[0][1].body;
 await expect(saveBuyerChange('update',row,{...updates,notes:'Different'})).rejects.toThrow('original');
 expect(state.api).toHaveBeenCalledTimes(1);
 await recoverBuyerChange('retry');expect(state.api.mock.calls[1][1].body).toBe(first);
});
it('a pending read retains the deletion and a durable stop resolves it',async()=>{
 state.api.mockRejectedValueOnce(new Error('Lost delete response'));
 await expect(saveBuyerChange('delete',row,null)).rejects.toThrow();
 const value=(await pendingBuyerChange())!;
 state.api.mockResolvedValueOnce(response({id:value.request_id,state:'pending'}));
 expect((await recoverBuyerChange('check'))?.state).toBe('pending');expect(await pendingBuyerChange()).not.toBeNull();
 state.api.mockResolvedValueOnce(response({id:value.request_id,state:'canceled'}));
 expect((await recoverBuyerChange('cancel'))?.state).toBe('canceled');expect(await pendingBuyerChange()).toBeNull();
});
it('blocks writes when storage is unavailable',async()=>{
 vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('Storage blocked');});
 await expect(saveBuyerChange('update',row,updates)).rejects.toThrow('Storage blocked');expect(state.api).not.toHaveBeenCalled();
});
it('does not accept a mismatched receipt or release the original request',async()=>{
 state.api.mockResolvedValueOnce(response(result(row.id)));
 await expect(saveBuyerChange('delete',row,null)).rejects.toThrow('unconfirmed');expect(await pendingBuyerChange()).not.toBeNull();
});
it('rejects a simultaneous mutation before it can overwrite the saved draft',async()=>{
 let release:(value:Response)=>void=()=>{};
 state.api.mockImplementationOnce((_path,init)=>new Promise<Response>(resolve=>{release=()=>resolve(response(result(JSON.parse(init.body).request_id)));}));
 const first=saveBuyerChange('update',row,updates);
 await vi.waitFor(()=>expect(state.api).toHaveBeenCalledTimes(1));
 await expect(saveBuyerChange('delete',row,null)).rejects.toThrow('already in progress');
 release(new Response());await first;expect(state.api).toHaveBeenCalledTimes(1);
});
