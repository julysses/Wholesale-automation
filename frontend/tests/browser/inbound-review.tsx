import React from 'react';
import {createRoot} from 'react-dom/client';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {InboundRequestQueue} from '../../src/components/acquisition/InboundRequestQueue';
import {IntakeReview} from '../../src/components/acquisition/IntakeReview';
import {PropertySources} from '../../src/components/acquisition/PropertySources';
import {scope,setDenied} from './inbound-review-api';
import '../../src/index.css';
export function Fixture(){return <main className="max-w-4xl mx-auto p-4 space-y-4"><h1 className="font-bold text-xl">Synthetic inbound review QA</h1><p>Local synthetic records. No database or provider connection; writes are rejected.</p><label className="flex gap-2 items-center"><input type="checkbox" onChange={e=>setDenied(e.target.checked)}/>Simulate revoked read access on refresh</label><InboundRequestQueue userId={scope.user} workspace={scope.workspace}/><IntakeReview userId={scope.user} workspace={scope.workspace}/><PropertySources userId={scope.user} workspace={scope.workspace} lead={scope.lead} property={scope.property}/></main>;}
createRoot(document.getElementById('root')!).render(<QueryClientProvider client={new QueryClient()}><Fixture/></QueryClientProvider>);
