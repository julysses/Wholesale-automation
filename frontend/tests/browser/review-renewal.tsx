import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReviewRenewalForm } from '../../src/components/acquisition/ReviewRenewalForm';
import { context } from '../review-renewal-fixture';
import { loseNextReply } from './review-renewal-api';
import '../../src/index.css';
export function Fixture() {
  const [held, setHeld] = useState(false);
  return <main className="max-w-3xl mx-auto p-4 space-y-4 text-[#1B3A5C]"><p className="rounded bg-amber-100 p-3 text-sm">Synthetic local preview. No live property, provider or agreement.</p><h1 className="text-xl font-bold">5. Review the contract</h1><p>123 Synthetic Street · Dallas</p><button className="rounded border p-2" onClick={loseNextReply}>Simulate lost reply</button><p>Workspace navigation: {held ? 'held' : 'available'}</p><ReviewRenewalForm context={context} disabled={false} onPending={setHeld} onSaved={() => undefined} /></main>;
}
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={new QueryClient()}><Fixture /></QueryClientProvider>);
