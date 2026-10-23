import {useState} from 'react';
import type {z} from 'zod';
import {reconciliationSchema,type LotAction} from '@/lib/lotWorkflow';
import {Button} from '@/components/ui/button';
type Props={handoffId:string;state:z.infer<typeof reconciliationSchema>;isAdmin:boolean;opened:boolean;locked:boolean;run:(action:LotAction)=>Promise<void>};
export function LotReconciliation({handoffId,state,isAdmin,opened,locked,run}:Props){
 const [notes,setNotes]=useState(''),[confirmed,setConfirmed]=useState(false);
 const allowed=!locked&&confirmed&&notes.trim().length>0&&notes.trim().length<=2000;
 function decide(action:'hold'|'reaffirm'){
  void run({kind:'reconcile',body:{request_id:crypto.randomUUID(),handoff_id:handoffId,expected_version:state.version,action,evidence_hash:state.evidence_hash,notes:notes.trim()}});
 }
 return <div className="rounded border p-3 space-y-2">
  <p>{state.current?'Handoff evidence and destination are current.':'Handoff requires review before relying on its underwriting evidence.'}</p>
  {state.reasons.length>0&&<p>Review reasons: {state.reasons.join(', ')}</p>}
  <details><summary>Current evidence for reconciliation</summary><pre className="whitespace-pre-wrap break-all text-sm">{JSON.stringify({property:state.property,destination:state.destination,latest_review:state.latest_review,latest_evaluation:state.latest_evaluation},null,2)}</pre></details>
  {state.last_decision&&<details><summary>Latest administrator decision</summary><pre className="whitespace-pre-wrap break-all text-sm">{JSON.stringify(state.last_decision,null,2)}</pre></details>}
  {isAdmin&&<>
   <label className="block">Reconciliation notes<textarea aria-label={`Reconciliation notes for ${handoffId}`} className="block w-full border rounded p-2" maxLength={2000} value={notes} onChange={e=>setNotes(e.target.value)} disabled={locked}/></label>
   <label className="block"><input type="checkbox" checked={confirmed} disabled={locked} onChange={e=>setConfirmed(e.target.checked)}/> I reviewed the current evidence and am recording a hold or reaffirmation, not approving an offer or completing underwriting.</label>
   <div className="flex gap-2">
    <Button disabled={!allowed} onClick={()=>decide('hold')}>Hold this handoff</Button>
    <Button disabled={!allowed||!opened||!state.reaffirmable} onClick={()=>decide('reaffirm')}>Reaffirm reviewed evidence</Button>
   </div>
   <p>Reaffirmation requires opening the linked land record and a current qualifying score, matching lot review, available assignee and matching destination. A hold remains available when the destination cannot be opened.</p>
  </>}
 </div>;
}
