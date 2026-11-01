import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BuyerProfiles } from '../../src/components/acquisition/BuyerProfiles';
import { loseNextReply } from './buyer-profiles-api';
import '../../src/index.css';
export function Fixture() {
  const [held, setHeld] = useState(false);
  return <main className="max-w-3xl mx-auto p-4 space-y-4 text-[#1B3A5C]"><p className="rounded bg-amber-100 p-3 text-sm">Synthetic local preview. No live property, provider or agreement.</p>
    <h1 className="text-xl font-bold">5. Review the contract</h1><p>123 Synthetic Street · Dallas</p><h2 className="font-semibold">Disposition review</h2>
    <button className="rounded border p-2" onClick={loseNextReply}>Simulate lost reply</button><p>Workspace navigation: {held ? 'held' : 'available'}</p>
    <BuyerProfiles userId="00000000-0000-4000-8000-000000000001" workspace="00000000-0000-4000-8000-000000000002" disabled={false} onPending={setHeld} /></main>;
}
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={new QueryClient()}><Fixture /></QueryClientProvider>);
