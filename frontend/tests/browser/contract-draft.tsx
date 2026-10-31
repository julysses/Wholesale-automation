import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ContractDraft } from '../../src/components/acquisition/ContractDraft';
import { ids, selected, loseNextReply } from './contract-draft-api';
import '../../src/index.css';
export function Fixture() {
  const [held, setHeld] = useState(false);
  return <main className="max-w-3xl mx-auto p-4 space-y-4"><p className="rounded bg-amber-100 p-3 text-sm">Local synthetic preview. No provider, database or live agreement.</p>
    <h1 className="text-xl font-bold text-[#1B3A5C]">5. Prepare a contract draft</h1>
    <button className="rounded border px-3 py-2" onClick={loseNextReply}>Simulate lost reply on next save</button>
    <p role="status">Workspace navigation: {held ? 'held for saved request' : 'available'}</p>
    <ContractDraft userId={ids.user} workspace={ids.workspace} selected={selected} onPending={setHeld} />
  </main>;
}
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={new QueryClient()}><Fixture /></QueryClientProvider>);
