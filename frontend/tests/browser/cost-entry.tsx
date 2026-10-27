import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {CostEntry} from '../../src/components/acquisition/CostEntry';
import {CampaignCosts} from '../../src/components/acquisition/CampaignCosts';
import {scope,link,setFault,count} from './cost-entry-api';
import '../../src/index.css';
export function Fixture(){const [pending,setPending]=useState(false);const [revision,setRevision]=useState(0);return <main className="max-w-4xl mx-auto p-4 space-y-4"><h1 className="font-bold text-xl">Synthetic cost entry QA</h1><p>No database, provider or spending actions. Reload resets the synthetic ledger.</p><label>Next simulated save<select className="block border p-2" onChange={e=>setFault(e.target.value)}><option value="none">Normal</option><option value="reject">Confirmed rejection</option><option value="lost">Save then lose response</option></select></label><p>Pending lock: {pending?'active':'clear'}</p><button className="border p-2" onClick={()=>setRevision(v=>v+1)}>Inspect synthetic ledger</button><p key={revision}>Recorded revisions: {count()}</p><CostEntry userId={scope.user} workspace={scope.workspace} intake={scope.intake} link={link} allowed locked={false} refreshLink={async()=>link} onPending={setPending}/><CampaignCosts userId={scope.user} workspace={scope.workspace} campaign={scope.campaign}/></main>;}
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={new QueryClient()}><Fixture/></QueryClientProvider>);
