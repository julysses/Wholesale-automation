import { fireEvent,render,screen } from '@testing-library/react';
import { beforeEach,expect,it,vi } from 'vitest';
const mocks=vi.hoisted(()=>({query:vi.fn(),refetch:vi.fn(),error:false}));
vi.mock('@/hooks/useLeads',()=>({useLeads:(filters:unknown)=>mocks.query(filters)}));
vi.mock('@/components/offers/OfferReview',()=>({OfferReview:({leadId}:{leadId:string})=><p>Review ID {leadId}</p>}));
import { OfferLeadPicker } from '@/components/offers/OfferLeadPicker';
beforeEach(()=>{
 vi.clearAllMocks();mocks.error=false;
 mocks.query.mockImplementation(({page,search}:{page:number;search:string})=>({
  data:{data:[{id:`lead-${search||page}`,property_address:`Property ${search||page}`,city:'Dallas'}],count:151},
  isLoading:false,error:mocks.error?new Error('Offline'):null,refetch:mocks.refetch,
 }));
});
it('pages beyond 100 and preserves the selected review while searching',()=>{
 render(<OfferLeadPicker/>);
 fireEvent.click(screen.getByRole('button',{name:'Next offer leads'}));
 fireEvent.click(screen.getByRole('button',{name:'Next offer leads'}));
 expect(mocks.query).toHaveBeenLastCalledWith({search:'',page:3,pageSize:50});
 fireEvent.change(screen.getByLabelText('Offer lead'),{target:{value:'lead-3'}});
 expect(screen.getByText('Review ID lead-3')).toBeTruthy();
 fireEvent.change(screen.getByLabelText('Find offer lead'),{target:{value:'Oak'}});
 expect(mocks.query).toHaveBeenLastCalledWith({search:'Oak',page:1,pageSize:50});
 expect(screen.getByLabelText('Offer lead')).toHaveValue('lead-3');
 expect(screen.getByText('Review ID lead-3')).toBeTruthy();
 fireEvent.change(screen.getByLabelText('Offer lead'),{target:{value:'lead-Oak'}});
 expect(screen.queryByText('Review ID lead-3')).toBeNull();
 expect(screen.getByText('Review ID lead-Oak')).toBeTruthy();
});
it('failed search is visible and cannot select another lead until recovery',()=>{
 mocks.error=true;render(<OfferLeadPicker/>);
 expect(screen.getByRole('alert')).toHaveTextContent('Offline');
 expect(screen.getByLabelText('Offer lead')).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Retry lead search'}));expect(mocks.refetch).toHaveBeenCalledOnce();
});
