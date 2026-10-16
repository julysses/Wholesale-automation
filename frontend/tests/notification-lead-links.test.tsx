import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const mock=vi.hoisted(()=>({rows:[] as Record<string,unknown>[], emit:null as null|((payload:{new:Record<string,unknown>})=>void), toast:vi.fn()}));
vi.mock('sonner',()=>({toast:{success:mock.toast,error:mock.toast}}));
vi.mock('@/lib/supabase',()=>({supabase:{
 from:()=>({select:()=>({order:()=>({limit:async()=>({data:mock.rows})})})}),
 channel:()=>({on:(_kind:unknown,_filter:unknown,callback:typeof mock.emit)=>{mock.emit=callback;return {subscribe:()=>({})};}}),
 removeChannel:vi.fn(),
}}));
import { useNotifications } from '@/hooks/useNotifications';
const id='11111111-1111-4111-8111-111111111111';
beforeEach(()=>{mock.rows=[];mock.emit=null;mock.toast.mockClear();});
it('routes saved generic lead alerts to their exact lead and preserves explicit destinations',async()=>{
 mock.rows=[{id:'one',lead_id:id,action_url:'/leads'}, {id:'two',lead_id:id,action_url:'/tasks'},
 {id:'three',lead_id:'invalid',action_url:'/leads'}, {id:'four',lead_id:id,action_url:'/leads?status=hot'}];
 const {result}=renderHook(()=>useNotifications());
 await waitFor(()=>expect(result.current.loading).toBe(false));
 expect(result.current.notifications.map(n=>n.action_url)).toEqual([`/leads?lead=${id}`,'/tasks','/leads','/leads?status=hot']);
 expect(mock.rows[0].action_url).toBe('/leads');
});
it('applies the same destination to live alert cards and high-priority toasts',async()=>{
 const {result}=renderHook(()=>useNotifications());
 await waitFor(()=>expect(result.current.loading).toBe(false));
 act(()=>mock.emit!({new:{id:'new',lead_id:id,action_url:'/leads',type:'hot_lead',title:'New inquiry',body:'Review it',read:false,metadata:{}}}));
 expect(result.current.notifications[0].action_url).toBe(`/leads?lead=${id}`);
 expect(mock.toast).toHaveBeenCalledWith(expect.any(String),expect.objectContaining({action:{label:'View',onClick:expect.any(Function)}}));
});
