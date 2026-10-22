import { act, renderHook } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const mocks=vi.hoisted(()=>({api:vi.fn()}));
vi.mock('@/lib/api',()=>({apiFetch:mocks.api}));
import { useCsvImport } from '@/hooks/useCsvImport';
beforeEach(()=>vi.clearAllMocks());
it('refuses an oversized request before submitting any rows',async()=>{
 const {result}=renderHook(()=>useCsvImport());
 const payload={rows:[{property_address:'123 Test St',city:'Dallas',seller_notes:'x'.repeat(4_500_001)}],
  engine:'rules' as const,score_with_claude:true,list_name:'Oversized',filename:'large.csv'};
 await act(async()=>{await expect(result.current(payload)).rejects.toThrow('no rows were submitted');});
 expect(mocks.api).not.toHaveBeenCalled();
});
it('keeps all 10000 short rows when the complete request fits the transport limit',async()=>{
 mocks.api.mockImplementation((_path:string,init:RequestInit)=>{
  const body=JSON.parse(init.body as string);
  return Promise.resolve(new Response(JSON.stringify({status:'ok',request_id:body.request_id,replayed:false,imported:10000,updated:0,
   consolidated_rows:10000,skipped:0,scored:10000,owner_review:0,scoring_state:'completed'})));
 });
 const {result}=renderHook(()=>useCsvImport());
 const payload={rows:Array.from({length:10000},(_,i)=>({property_address:`${i} Synthetic St`,city:'Dallas',state:'TX'})),
  engine:'rules' as const,score_with_claude:true,list_name:'Full upload',filename:'full.csv'};
 await act(async()=>{await expect(result.current(payload)).resolves.toMatchObject({imported:10000});});
 expect(mocks.api).toHaveBeenCalledTimes(1);
 expect(JSON.parse(mocks.api.mock.calls[0][1].body).rows).toHaveLength(10000);
});
