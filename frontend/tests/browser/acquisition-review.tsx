import React from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AcquisitionReview } from '../../src/pages/AcquisitionReview';
import '../../src/index.css';
createRoot(document.getElementById('root')!).render(<React.StrictMode><QueryClientProvider client={new QueryClient()}>
  <div className="bg-amber-100 text-amber-900 text-center p-2">Local QA fixture · synthetic data · no live actions</div>
  <AcquisitionReview userId="fixture-reviewer" />
</QueryClientProvider></React.StrictMode>);
