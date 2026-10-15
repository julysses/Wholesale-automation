import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
const mocks=vi.hoisted(()=>({limit:vi.fn(),on:vi.fn(),remove:vi.fn()}));
vi.mock('@/lib/supabase',()=>({supabase:{
 from:()=>({select:()=>({order:()=>({limit:mocks.limit})})}),
 channel:()=>({on:(_event:unknown,_filter:unknown,callback:unknown)=>{mocks.on(callback);return {subscribe:()=>({})};}}),
 removeChannel:mocks.remove,
}}));
vi.mock('sonner',()=>({toast:{success:vi.fn(),error:vi.fn()}}));
import {useNotifications} from '@/hooks/useNotifications';
afterEach(()=>{vi.useRealTimers();vi.clearAllMocks();});
it('refreshes a daily alert without duplicates and polls when Realtime is unavailable',async()=>{
 const original={id:'daily',type:'pipeline_step',read:true,metadata:{property_count:1}};
 mocks.limit.mockResolvedValue({data:[original],error:null});
 const hook=renderHook(()=>useNotifications());
 await waitFor(()=>expect(hook.result.current.notifications).toHaveLength(1));
 act(()=>mocks.on.mock.calls[0][0]({eventType:'UPDATE',new:{...original,read:false,metadata:{property_count:2}}}));
 expect(hook.result.current.notifications).toHaveLength(1);
 expect(hook.result.current.unreadCount).toBe(1);
 expect(hook.result.current.notifications[0].metadata.property_count).toBe(2);
 vi.useFakeTimers();
 hook.unmount();
 const polling=renderHook(()=>useNotifications());
 await act(async()=>{});
 mocks.limit.mockResolvedValue({data:[{...original,metadata:{property_count:3}}],error:null});
 await act(async()=>{await vi.advanceTimersByTimeAsync(60000);});
 expect(polling.result.current.notifications[0].metadata.property_count).toBe(3);
 mocks.limit.mockResolvedValue({data:null,error:new Error('offline')});
 await act(async()=>{await vi.advanceTimersByTimeAsync(60000);});
 expect(polling.result.current.notifications).toHaveLength(1);
 polling.unmount();expect(vi.getTimerCount()).toBe(0);
});
