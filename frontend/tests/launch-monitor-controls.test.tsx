import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { LaunchMonitorPanel } from '../src/components/LaunchMonitorPanel';
const mocks=vi.hoisted(()=>({api:vi.fn()}));
vi.mock('../src/lib/api',()=>({apiFetch:mocks.api}));
beforeEach(()=>{mocks.api.mockReset();}); afterEach(cleanup);
const state={snapshot:{database:true,intake:true,owner:true,aged:{intake:1},open_incidents:1},incidents:[{id:'incident',category:'intake',reference:'receipt',first_seen:'2026-10-08T10:00:00Z'}]};
const reply=(value:unknown)=>({json:async()=>value});
test('opening monitoring is read only and shows actual backlog',async()=>{
 mocks.api.mockResolvedValue(reply(state)); render(<LaunchMonitorPanel/>);
 await screen.findByText('Open monitor incidents: 1');
 expect(screen.getByText('intake: 1 aged outcomes need review')).toBeInTheDocument();
 expect(mocks.api.mock.calls.every(call=>call[0]==='/api/operations/monitor'&&!call[1]?.method)).toBe(true);
});
test('manual scan reports durable receipt then refreshes evidence',async()=>{
 mocks.api.mockResolvedValueOnce(reply(state)).mockResolvedValueOnce(reply({created:0})).mockResolvedValueOnce(reply(state));
 render(<LaunchMonitorPanel/>); await screen.findByText('Open monitor incidents: 1');
 fireEvent.click(screen.getByRole('button',{name:'Scan stalled work'}));
 await screen.findByText('0 new escalations saved. No seller outreach was replayed.');
 expect(mocks.api.mock.calls.filter(call=>call[1]?.method==='POST')).toHaveLength(1);
});
test('unavailable storage remains a visible failure',async()=>{
 mocks.api.mockRejectedValue(new Error('Monitoring database unavailable'));
 render(<LaunchMonitorPanel/>); await screen.findByText('Monitoring database unavailable');
 expect(screen.queryByText(/Database: available/)).not.toBeInTheDocument();
});
