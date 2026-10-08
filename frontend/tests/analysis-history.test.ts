import { beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ from: vi.fn(), range: vi.fn(), eq: vi.fn(), order: vi.fn(), failed: false }));
vi.mock('@/lib/supabase', () => ({ supabase: {from:mocks.from} }));
import { loadAnalysisPage } from '@/lib/analysisHistory';
beforeEach(()=>{
 vi.clearAllMocks();mocks.failed=false;
 mocks.from.mockImplementation((table:string)=>{
  const chain={select:vi.fn().mockReturnThis(),order:mocks.order,range:mocks.range,eq:mocks.eq,in:vi.fn().mockReturnThis()};
  mocks.order.mockReturnValue(chain);mocks.eq.mockReturnValue(chain);
  mocks.range.mockImplementation(async()=> mocks.failed ? {data:null,count:null,error:{message:'Database unavailable'}} : table==='deal_analyses' ? {data:[{id:'older-rejected',lead_id:null,is_viable:false,mao:0}],count:101,error:null} : {data:[],error:null});
  return chain;
 });
});
it('keeps rejected zero-MAO analyses and reads older pages without a viable filter',async()=>{
 const result=await loadAnalysisPage(3);
 expect(result.count).toBe(101);expect(result.data[0]).toMatchObject({id:'older-rejected',is_viable:false,mao:0});
 expect(mocks.eq).not.toHaveBeenCalled();expect(mocks.range).toHaveBeenCalledWith(100,149);
 expect(mocks.order).toHaveBeenCalledWith('id',{ascending:false});
});
it('does not convert a failed history read to an empty successful list',async()=>{
 mocks.failed=true;
 await expect(loadAnalysisPage(1)).rejects.toMatchObject({message:'Database unavailable'});
});
