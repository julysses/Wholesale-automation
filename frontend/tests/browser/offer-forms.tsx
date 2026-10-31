import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CampaignDrafts } from '../../src/components/acquisition/CampaignDrafts';
import { ids, loseNextReply } from './offer-forms-api';
import '../../src/index.css';
export function Fixture() {
  const [held, setHeld] = useState(false);
  return <main className="max-w-3xl mx-auto p-4 space-y-4"><h1 className="text-xl font-bold text-[#1B3A5C]">1. Prepare campaigns</h1><p className="text-sm">Synthetic preview only. No provider, database, public seller form or outreach.</p><button className="rounded border px-3 py-2" onClick={loseNextReply}>Simulate lost reply on next save</button><p role="status">Workspace navigation: {held ? 'held for saved request' : 'available'}</p><CampaignDrafts userId={ids.user} workspace={ids.workspace} onPending={setHeld}/></main>;
}
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={new QueryClient()}><Fixture/></QueryClientProvider>);
