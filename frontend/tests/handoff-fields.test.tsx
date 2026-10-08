import { useState } from 'react';
import { fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
const options = vi.hoisted(() => ({failed:false}));
vi.mock('@tanstack/react-query', () => ({useQuery: ({queryKey}: {queryKey:string[]}) => ({data: queryKey[0] === 'handoff_owners' ? [{id:'owner-qa',full_name:'QA Owner'}] : [{id:'buyer-qa',first_name:'QA',last_name:'Buyer'}], error:options.failed ? new Error('Offline') : null})}));
import { DealHandoffFields } from '@/components/pipeline/DealHandoffFields';
import type { DealWrite } from '@/hooks/useDeals';
afterEach(() => { cleanup(); options.failed=false; });
it('retains evidence and explicitly clears money, dates and buyer', () => {
  const changed=vi.fn();
  function Harness() {
    const [value,set]=useState<DealWrite>({assigned_to:'owner-qa',buyer_id:'buyer-qa',earnest_money:1000,inspection_deadline:'2026-10-09',psa_doc_url:'https://example.com/qa'});
    return <DealHandoffFields value={value} onChange={next=>{set(next);changed(next);}}/>;
  }
  render(<Harness/>);
  expect((screen.getByLabelText('Responsible owner') as HTMLSelectElement).value).toBe('owner-qa');
  fireEvent.change(screen.getByLabelText('Earnest money'),{target:{value:''}});
  fireEvent.change(screen.getByLabelText('Inspection deadline'),{target:{value:''}});
  fireEvent.change(screen.getByLabelText('Selected buyer'),{target:{value:''}});
  expect(changed.mock.lastCall?.[0]).toMatchObject({earnest_money:null,inspection_deadline:null,buyer_id:null,assigned_to:'owner-qa',psa_doc_url:'https://example.com/qa'});
});
it('preserves current assignments when loading options fails', () => {
  options.failed=true;
  render(<DealHandoffFields value={{assigned_to:'unloaded-owner',buyer_id:'unloaded-buyer'}} onChange={vi.fn()}/>);
  expect(screen.getByRole('alert').textContent).toContain('could not be loaded');
  expect((screen.getByLabelText('Responsible owner') as HTMLSelectElement).value).toBe('unloaded-owner');
  expect((screen.getByLabelText('Selected buyer') as HTMLSelectElement).value).toBe('unloaded-buyer');
});
