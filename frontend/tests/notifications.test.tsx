import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { AppNotification } from '@/hooks/useNotifications';
const mock=vi.hoisted(()=>({read:vi.fn(),write:vi.fn(),success:vi.fn(),error:vi.fn(),callbacks:{} as Record<string,(payload:{new:AppNotification})=>void>}));
vi.mock('sonner',()=>({toast:{success:mock.success,error:mock.error}}));
vi.mock('@/lib/supabase',()=>({supabase:{
 from:()=>({select:()=>({order:()=>({limit:mock.read})}),update:()=>({eq:mock.write,in:mock.write})}),
 channel:()=>{const channel={on:(_kind:string,filter:{event:string},cb:(payload:{new:AppNotification})=>void)=>{mock.callbacks[filter.event]=cb;return channel;},subscribe:()=>channel};return channel;},removeChannel:vi.fn(),
}}));
import { useNotifications } from '@/hooks/useNotifications';
const row=(id:string):AppNotification=>({id,created_at:'2026-10-19T19:26:50Z',type:'pipeline_step',title:'SMS reply received',body:'Please call ASAP',action_url:'/leads',action_label:null,lead_id:'11111111-1111-4111-8111-111111111111',deal_id:null,read:false,read_at:null,metadata:{provider:'twilio'}});
beforeEach(()=>{vi.clearAllMocks();mock.callbacks={};mock.read.mockResolvedValue({data:[],error:null});mock.write.mockResolvedValue({error:null});});
it('recovers missed replies on focus, deep-links, and announces each receipt only once',async()=>{
 const {result}=renderHook(useNotifications);await waitFor(()=>expect(result.current.loading).toBe(false));
 mock.read.mockResolvedValue({data:[row('new')],error:null});
 act(()=>window.dispatchEvent(new Event('focus')));
 await waitFor(()=>expect(result.current.unreadCount).toBe(1));
 expect(result.current.notifications[0].action_url).toContain('?lead=11111111');expect(mock.success).toHaveBeenCalledTimes(1);
 await act(()=>result.current.refresh());act(()=>mock.callbacks.INSERT({new:row('new')}));
 await waitFor(()=>expect(mock.read).toHaveBeenCalledTimes(4));expect(mock.success).toHaveBeenCalledTimes(1);expect(result.current.notifications).toHaveLength(1);
});
it('does not replay historical alerts; preserves saved list on fetch failure and recovers',async()=>{
 mock.read.mockResolvedValue({data:[row('old')],error:null});const {result}=renderHook(useNotifications);
 await waitFor(()=>expect(result.current.unreadCount).toBe(1));expect(mock.success).not.toHaveBeenCalled();
 mock.read.mockResolvedValue({data:null,error:{message:'private'}});await act(()=>result.current.refresh());
 expect(result.current.notifications).toHaveLength(1);expect(result.current.error).toContain('could not refresh');
 mock.read.mockResolvedValue({data:[row('old'),row('new')],error:null});await act(()=>result.current.refresh());
 expect(result.current.error).toBeNull();expect(mock.success).toHaveBeenCalledTimes(1);
});
it('ignores a delayed snapshot after a newer realtime reply',async()=>{
 let resolve!: (value:unknown)=>void;
 mock.read.mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));
 const {result}=renderHook(useNotifications);mock.read.mockResolvedValue({data:[row('new')],error:null});
 act(()=>mock.callbacks.INSERT({new:row('new')}));await waitFor(()=>expect(result.current.unreadCount).toBe(1));
 await act(async()=>resolve({data:[],error:null}));expect(result.current.notifications[0].id).toBe('new');expect(mock.success).toHaveBeenCalledTimes(1);
});
it('does not mark read on a rejected write or mark a newly arriving receipt read with an older batch',async()=>{
 mock.read.mockResolvedValue({data:[row('old')],error:null});const {result}=renderHook(useNotifications);await waitFor(()=>expect(result.current.unreadCount).toBe(1));
 mock.write.mockResolvedValueOnce({error:{message:'denied'}});await act(()=>result.current.markRead('old'));expect(result.current.unreadCount).toBe(1);
 let resolve!: (value:unknown)=>void;mock.write.mockImplementationOnce(()=>new Promise(r=>{resolve=r;}));
 let pending!:Promise<void>;act(()=>{pending=result.current.markAllRead();});
 mock.read.mockResolvedValue({data:[row('new'),row('old')],error:null});act(()=>mock.callbacks.INSERT({new:row('new')}));await waitFor(()=>expect(result.current.unreadCount).toBe(2));
 await act(async()=>{resolve({error:null});await pending;});expect(result.current.notifications.find(n=>n.id==='new')?.read).toBe(false);expect(result.current.unreadCount).toBe(1);
});
