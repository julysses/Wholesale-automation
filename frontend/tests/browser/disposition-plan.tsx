import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DispositionPlanForm } from '../../src/components/acquisition/DispositionPlanForm';
import { context } from '../fixtures/disposition-plan';
import { loseNextReply, pause } from './disposition-plan-api';
import '../../src/index.css';
export function Fixture() {
  const [held, setHeld] = useState(false);
  return <main className="max-w-3xl mx-auto p-4 space-y-4"><p className="rounded bg-amber-100 p-3 text-sm">Synthetic local preview. No live property, provider or agreement.</p><h1 className="text-xl font-bold text-[#1B3A5C]">5. Review the contract</h1><p>123 Synthetic Street · Dallas</p><div className="flex flex-wrap gap-2"><button className="rounded border p-2" onClick={loseNextReply}>Simulate lost reply</button><button className="rounded border p-2" onClick={pause}>Pause test acquisition</button></div><p>Workspace navigation: {held ? 'held' : 'available'}</p><DispositionPlanForm context={context} disabled={false} onPending={setHeld} onSaved={() => undefined} /></main>;
}
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={new QueryClient()}><Fixture /></QueryClientProvider>);
