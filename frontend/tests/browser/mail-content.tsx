import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MailContentReviews } from '../../src/components/acquisition/MailContentReviews';
import { ids, setFault, setRole, count } from './mail-content-api';
import '../../src/index.css';
export function Fixture() {
  const [held, setHeld] = useState(false), [revision, setRevision] = useState(0);
  return <main className="max-w-4xl mx-auto p-4 space-y-4"><h1 className="font-bold text-xl text-[#1B3A5C]">Prepare this mailing</h1><p>Synthetic QA only. No real approval, provider, database or fulfillment. Test decisions survive reload in this tab.</p>
    <div className="flex flex-wrap gap-3"><label>Next simulated save<select className="block border p-2" onChange={e => setFault(e.target.value)}><option value="none">Normal</option><option value="lost">Save then lose response</option><option value="reject">Confirmed rejection</option></select></label><label>Simulated role<select className="block border p-2" onChange={e => setRole(e.target.value)}><option value="owner">Owner</option><option value="operator">Operator</option></select></label><button className="border p-2" onClick={() => setRevision(v => v + 1)}>Inspect synthetic ledger</button></div>
    <p key={revision}>Recorded decisions: {count()} · Navigation held: {held ? 'yes' : 'no'}</p><div className="border rounded-xl bg-gray-50 p-4"><h2 className="font-semibold text-[#1B3A5C]">3. Review content and preview</h2><MailContentReviews userId={ids.user} workspace={ids.workspace} campaign={ids.campaign} onPending={(_, pending) => setHeld(pending)}/></div></main>;
}
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={new QueryClient()}><Fixture/></QueryClientProvider>);
