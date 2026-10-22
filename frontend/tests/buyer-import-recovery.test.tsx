import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const mocks=vi.hoisted(()=>({api:vi.fn(),imported:vi.fn()}));
vi.mock('@/lib/api',()=>({apiFetch:mocks.api}));
vi.mock('papaparse',()=>({default:{parse:(_file:File,options:{complete:(value:unknown)=>void})=>options.complete({meta:{fields:['Grantee','Property Address']},data:[{Grantee:'QA LLC','Property Address':'100 Test St'}]})}}));
vi.mock('sonner',()=>({toast:{error:vi.fn(),success:vi.fn()}}));
import { BuyerImportModal } from '@/components/buyers/BuyerImportModal';
function upload(){
 render(<BuyerImportModal open onClose={()=>{}} onImported={mocks.imported}/>);
 fireEvent.change(screen.getByLabelText('Buyer CSV file'),{target:{files:[new File(['Grantee,Property Address\nQA LLC,100 Test St\n'],'test.csv',{type:'text/csv'})]}});
}
function complete(reference:string){return {ok:true,status:200,json:async()=>({status:'complete',import_id:reference,import_log_id:reference,replayed:false,outreach_authorized:false,
 buyers_created:1,buyers_existing:0,transactions_created:1,transactions_existing:0,rows_total:1,rows_skipped:0,buyer_ids:['00000000-0000-4000-8000-000000000001']})};}
beforeEach(()=>{mocks.api.mockReset();mocks.imported.mockReset();});
it('confirms committed counts before refreshing the buyer list',async()=>{
 mocks.api.mockImplementation(async(_path,options)=>complete(options.body.get('request_id')));
 upload();fireEvent.click(screen.getByRole('button',{name:'Import test.csv'}));
 await screen.findByText('Import saved and confirmed');
 expect(mocks.imported).toHaveBeenCalledTimes(1);
 expect(screen.queryByText(/queued successfully/)).not.toBeInTheDocument();
});
it('recovers an uncertain result with the exact original reference and file',async()=>{
 mocks.api.mockRejectedValueOnce(new Error('Connection lost'));
 mocks.api.mockImplementationOnce(async(_path,options)=>complete(options.body.get('request_id')));
 upload();fireEvent.click(screen.getByRole('button',{name:'Import test.csv'}));
 await screen.findByRole('alert');
 expect(mocks.imported).not.toHaveBeenCalled();
 expect(screen.getByRole('button',{name:'Back'})).toBeDisabled();
 fireEvent.click(screen.getByRole('button',{name:'Retry original import'}));
 await screen.findByText('Import saved and confirmed');
 const first=mocks.api.mock.calls[0][1].body as FormData;
 const second=mocks.api.mock.calls[1][1].body as FormData;
 expect(first.get('request_id')).toBe(second.get('request_id'));
 expect(first.get('file')).toBe(second.get('file'));
 expect(mocks.imported).toHaveBeenCalledTimes(1);
});
it.each(['processing','wrong reference','partial counts'])('refuses %s as saved evidence',async kind=>{
 mocks.api.mockImplementation(async(_path,options)=>{
  const data=await complete(options.body.get('request_id')).json();
  if(kind==='processing')data.status='processing';
  if(kind==='wrong reference')data.import_id='another-reference';
  if(kind==='partial counts')data.transactions_created=0;
  return {ok:true,json:async()=>data};
 });
 upload();fireEvent.click(screen.getByRole('button',{name:'Import test.csv'}));
 await screen.findByRole('alert');
 expect(mocks.imported).not.toHaveBeenCalled();
 expect(screen.queryByText('Import saved and confirmed')).not.toBeInTheDocument();
});
it('does not turn a confirmed import into another write if list refresh throws',async()=>{
 mocks.api.mockImplementation(async(_path,options)=>complete(options.body.get('request_id')));
 mocks.imported.mockImplementation(()=>{throw new Error('Refresh failed');});
 upload();fireEvent.click(screen.getByRole('button',{name:'Import test.csv'}));
 await screen.findByText('Import saved and confirmed');
 await waitFor(()=>expect(mocks.api).toHaveBeenCalledTimes(1));
});
