import React, {useState} from 'react';
import {createRoot} from 'react-dom/client';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {MailDestinations} from '../../src/components/acquisition/MailDestinations';
import {scope,setFault,setRole,count} from './mail-destinations-api';
import '../../src/index.css';
export function Fixture(){const [revision,setRevision]=useState(0);return <main className="max-w-4xl mx-auto p-4 space-y-4"><h1 className="font-bold text-xl">Synthetic destination review QA</h1><p>Test evidence only. No real approval, database, provider or fulfillment. The synthetic ledger survives reload in this tab.</p><label>Next simulated save<select className="block border p-2" onChange={e=>setFault(e.target.value)}><option value="none">Normal</option><option value="lost">Save then lose response</option><option value="reject">Confirmed rejection</option></select></label><label>Simulated role<select className="block border p-2" onChange={e=>setRole(e.target.value)}><option value="owner">Owner</option><option value="operator">Operator</option></select></label><button className="border p-2" onClick={()=>setRevision(v=>v+1)}>Inspect synthetic ledger</button><p key={revision}>Recorded reviews: {count()}</p><MailDestinations userId={scope.user} workspace={scope.workspace} campaign={scope.campaign}/></main>;}
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={new QueryClient()}><Fixture/></QueryClientProvider>);
