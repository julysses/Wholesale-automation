import { useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  BarChart3, Building2, Calculator, CheckCircle2, ClipboardCheck, Download,
  Landmark, Plus, Save, ShieldAlert, Trash2, Upload, WalletCards,
} from 'lucide-react';
import { supabase } from '@/lib/supabase';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import {
  calculateProject, createProject, createWorkspace, portfolioEquityNeed, recommendedExit,
  parseWorkspace, workspaceStorageKey, treasuryForecast, rentPerUnitFromSf,
  type CashItem, type DevelopmentCost, type DevelopmentGate, type DevelopmentProject,
  type DevelopmentSettings, type DevelopmentWorkspace,
} from '@/lib/developmentEngine';

type Tab = 'overview' | 'spec' | 'btr' | 'costs' | 'delivery' | 'acquisitions' | 'capital' | 'plan';
const tabs: Array<[Tab, string, React.ElementType]> = [
  ['overview', 'Command Center', BarChart3], ['spec', 'Spec Build', Building2],
  ['btr', 'Build to Rent', Landmark], ['costs', 'Cost Control', Calculator],
  ['delivery', 'Delivery', ClipboardCheck], ['acquisitions', 'Acquisitions', Plus],
  ['capital', 'Capital', WalletCards], ['plan', 'Operating Plan', CheckCircle2],
];

const currency = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const money = (value: number) => Number.isFinite(value) ? currency.format(value) : '—';
const pct = (value: number | null) => value === null ? 'N/M' : `${value.toFixed(1)}%`;
const multiple = (value: number | null) => value === null ? 'N/M' : `${value.toFixed(2)}x`;

function NumberField({ label, value, onChange, min = 0, step = 1, suffix }: {
  label: string; value: number; onChange: (value: number) => void; min?: number; step?: number; suffix?: string;
}) {
  return <div className="space-y-1">
    <label className="block text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</label>
    <div className="relative">
      <input aria-label={label} type="number" min={min} step={step} value={Number.isFinite(value) ? value : 0}
        onChange={event => onChange(Number(event.target.value) || 0)}
        className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 pr-10 text-sm focus:border-[#9D1C20] focus:outline-none focus:ring-1 focus:ring-[#9D1C20]" />
      {suffix && <span className="absolute right-3 top-2 text-sm text-gray-400">{suffix}</span>}
    </div>
  </div>;
}

function SelectField({ label, value, options, onChange }: {
  label: string; value: string; options: string[]; onChange: (value: string) => void;
}) {
  return <label className="space-y-1">
    <span className="block text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</span>
    <select aria-label={label} value={value} onChange={event => onChange(event.target.value)}
      className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:border-[#9D1C20] focus:outline-none focus:ring-1 focus:ring-[#9D1C20]">
      {options.map(option => <option key={option}>{option}</option>)}
    </select>
  </label>;
}

function Metric({ label, value, note, bad = false }: { label: string; value: string; note?: string; bad?: boolean }) {
  return <div className={cn('rounded-lg border bg-white p-4', bad ? 'border-red-200 bg-red-50' : 'border-gray-200')}>
    <div className="text-xs font-semibold uppercase tracking-wide text-gray-500">{label}</div>
    <div className={cn('mt-1 text-xl font-bold', bad ? 'text-red-700' : 'text-gray-900')}>{value}</div>
    {note && <div className="mt-1 text-xs text-gray-500">{note}</div>}
  </div>;
}

function Section({ title, subtitle, action, children }: {
  title: string; subtitle?: string; action?: React.ReactNode; children: React.ReactNode;
}) {
  return <Card>
    <CardHeader className="flex flex-row items-start justify-between gap-4">
      <div><CardTitle>{title}</CardTitle>{subtitle && <p className="mt-1 text-sm text-gray-500">{subtitle}</p>}</div>{action}
    </CardHeader>
    <CardContent>{children}</CardContent>
  </Card>;
}

function editableCost(project: DevelopmentProject, sf: number, row: DevelopmentCost, update: (row: DevelopmentCost) => void) {
  const field = (key: keyof DevelopmentCost, value: number | string) => update({ ...row, [key]: value });
  return <tr key={row.id} className="border-b border-gray-100 last:border-0">
    <td className="py-2 pr-3"><input aria-label={`${row.name} name`} value={row.name} onChange={e => field('name', e.target.value)} className="min-w-48 rounded border px-2 py-1.5 text-sm" /></td>
    <td className="py-2 pr-3 text-xs text-gray-500">{row.group}</td>
    <td className="py-2 pr-3"><input aria-label={`${row.name} budget`} type="number" value={row.budget} onChange={e => field('budget', +e.target.value)} className="w-28 rounded border px-2 py-1.5 text-sm" /></td>
    <td className="py-2 pr-3"><input aria-label={`${row.name} cost per square foot`} type="number" step=".01" value={(row.budget / Math.max(1, sf)).toFixed(2)} onChange={e => field('budget', +e.target.value * sf)} className="w-24 rounded border px-2 py-1.5 text-sm" /></td>
    <td className="py-2 pr-3"><input aria-label={`${row.name} committed`} type="number" value={row.committed} onChange={e => field('committed', +e.target.value)} className="w-28 rounded border px-2 py-1.5 text-sm" /></td>
    <td className="py-2 pr-3"><input aria-label={`${row.name} incurred`} type="number" value={row.incurred} onChange={e => field('incurred', +e.target.value)} className="w-28 rounded border px-2 py-1.5 text-sm" /></td>
    <td className="py-2 pr-3"><input aria-label={`${row.name} paid`} type="number" value={row.paid} onChange={e => field('paid', +e.target.value)} className="w-28 rounded border px-2 py-1.5 text-sm" /></td>
    <td className="py-2"><input aria-label={`${row.name} remaining`} type="number" value={row.remaining} onChange={e => field('remaining', +e.target.value)} className="w-28 rounded border px-2 py-1.5 text-sm" /></td>
  </tr>;
}

export function DevelopmentCommandCenter({ userId }: { userId: string }) {
  const storageKey = workspaceStorageKey(userId);
  const revision = useRef(0);
  const [workspace, setWorkspace] = useState<DevelopmentWorkspace>(() => {
    try { return parseWorkspace(JSON.parse(localStorage.getItem(storageKey) || '')); } catch { return createWorkspace(); }
  });
  const [activeId, setActiveId] = useState(workspace.projects[0]?.id ?? '');
  const [tab, setTab] = useState<Tab>('overview');
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);
  const importRef = useRef<HTMLInputElement>(null);
  const project = workspace.projects.find(item => item.id === activeId) ?? workspace.projects[0];
  const settings = workspace.settings;
  const metrics = useMemo(() => calculateProject(project, settings), [project, settings]);
  const stress = useMemo(() => calculateProject(project, settings, true), [project, settings]);
  const developmentNeed = useMemo(() => portfolioEquityNeed(workspace), [workspace]);
  const treasury = useMemo(() => treasuryForecast(workspace), [workspace]);
  const protectedReserve = settings.monthlyOverhead * settings.reserveMonths;
  const headroom = settings.liquidity - protectedReserve - developmentNeed;

  useEffect(() => {
    let live = true;
    // An operator's local draft takes precedence over the last cloud save.
    let hasDraft = false;
    try { parseWorkspace(JSON.parse(localStorage.getItem(storageKey) || '')); hasDraft = true; } catch { /* no valid draft */ }
    const initialRevision = revision.current;
    void (async () => {
      const { data: saved, error } = await supabase.from('development_workspaces').select('workspace').eq('user_id', userId).maybeSingle();
      if (!live || hasDraft || revision.current !== initialRevision || error || !saved) return;
      try {
        const loaded = parseWorkspace(saved.workspace);
        setWorkspace(loaded);
        setActiveId(loaded.projects[0].id);
        setDirty(false);
      } catch { toast.error('Cloud workspace is invalid; your local workspace is unchanged.'); }
    })().catch(() => undefined);
    return () => { live = false; };
  }, [userId, storageKey]);

  const mutate = (fn: (current: DevelopmentWorkspace) => DevelopmentWorkspace) => {
    revision.current += 1;
    setWorkspace(current => {
      const next = fn(current);
      localStorage.setItem(storageKey, JSON.stringify(next));
      return next;
    });
    setDirty(true);
  };
  const updateProject = (patch: Partial<DevelopmentProject>) => mutate(current => ({
    ...current, projects: current.projects.map(item => item.id === project.id ? { ...item, ...patch } : item),
  }));
  const updateSettings = (patch: Partial<DevelopmentSettings>) => mutate(current => ({ ...current, settings: { ...current.settings, ...patch } }));

  const save = async () => {
    setSaving(true);
    const savingRevision = revision.current;
    localStorage.setItem(storageKey, JSON.stringify(workspace));
    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user || user.id !== userId) throw new Error('Your account changed. Reload before saving.');
      const { error } = await supabase.from('development_workspaces').upsert({ user_id: user.id, workspace, updated_at: new Date().toISOString() }, { onConflict: 'user_id' });
      if (error) throw error;
      if (revision.current === savingRevision) setDirty(false);
      toast.success('Development workspace saved');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Saved locally; cloud sync failed');
    } finally { setSaving(false); }
  };
  const addProject = () => {
    const next = createProject();
    mutate(current => ({ ...current, projects: [...current.projects, next] }));
    setActiveId(next.id); setTab('spec');
  };
  const removeProject = () => {
    if (workspace.projects.length === 1 || !window.confirm(`Remove ${project.name}?`)) return;
    const remaining = workspace.projects.filter(item => item.id !== project.id);
    mutate(current => ({ ...current, projects: remaining }));
    setActiveId(remaining[0].id);
  };
  const exportWorkspace = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(workspace, null, 2)], { type: 'application/json' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = `Hilltop-development-${new Date().toISOString().slice(0, 10)}.json`; anchor.click();
    URL.revokeObjectURL(url);
  };
  const importWorkspace = async (file?: File) => {
    if (!file) return;
    try {
      const parsed = parseWorkspace(JSON.parse(await file.text()));
      mutate(() => parsed); setActiveId(parsed.projects[0].id); toast.success('Workspace imported');
    } catch { toast.error('Choose a valid Hilltop development JSON export'); }
  };

  const updateCost = (row: DevelopmentCost) => updateProject({ costs: project.costs.map(item => item.id === row.id ? row : item) });
  const updateGate = (gate: DevelopmentGate) => updateProject({ gates: project.gates.map(item => item.id === gate.id ? gate : item) });

  return <div className="space-y-5">
    <div className="rounded-xl bg-[#9D1C20] px-5 py-5 text-white shadow-sm">
      <div className="flex flex-col justify-between gap-4 xl:flex-row xl:items-center">
        <div className="flex items-center gap-3"><div className="flex h-11 w-11 items-center justify-center rounded-lg bg-white text-xl font-black text-[#9D1C20]">H.</div>
          <div><h1 className="text-2xl font-bold">Development Command Center</h1><p className="text-sm text-red-100">Screen, capitalize, build, sell or retain every Hilltop opportunity.</p></div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className="border-white/40 bg-white/10 text-white hover:bg-white/20" icon={<Plus className="h-4 w-4" />} onClick={addProject}>New project</Button>
          <Button variant="outline" className="border-white/40 bg-white/10 text-white hover:bg-white/20" icon={<Download className="h-4 w-4" />} onClick={exportWorkspace}>Export</Button>
          <Button variant="outline" className="border-white/40 bg-white/10 text-white hover:bg-white/20" icon={<Upload className="h-4 w-4" />} onClick={() => importRef.current?.click()}>Import</Button>
          <input ref={importRef} type="file" accept="application/json,.json" className="hidden" onChange={e => importWorkspace(e.target.files?.[0])} />
          <Button className="bg-white text-[#9D1C20] hover:bg-red-50" loading={saving} icon={<Save className="h-4 w-4" />} onClick={save}>{dirty ? 'Save changes' : 'Saved'}</Button>
        </div>
      </div>
    </div>

    <div className="grid gap-4 xl:grid-cols-[260px_minmax(0,1fr)]">
      <aside className="space-y-4">
        <Card><CardContent className="p-3">
          <label className="text-xs font-semibold uppercase tracking-wide text-gray-500">Selected project</label>
          <select value={project.id} onChange={e => setActiveId(e.target.value)} className="mt-1 w-full rounded-md border px-3 py-2 text-sm">
            {workspace.projects.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}
          </select>
          <div className="mt-3 space-y-1">{tabs.map(([key, label, Icon]) => <button key={key} onClick={() => setTab(key)}
            className={cn('flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm font-medium', tab === key ? 'bg-[#9D1C20] text-white' : 'text-gray-600 hover:bg-gray-100')}>
            <Icon className="h-4 w-4" />{label}</button>)}</div>
        </CardContent></Card>
        <Card><CardContent className="space-y-2 p-4 text-sm">
          <div className="font-semibold text-gray-900">Investment decision</div>
          <div className={cn('rounded-md px-3 py-2 font-semibold', metrics.salePass || metrics.rentalPass ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700')}>{recommendedExit(project, settings)}</div>
          <div className="flex justify-between"><span className="text-gray-500">Stage</span><span>{project.stage}</span></div>
          <div className="flex justify-between"><span className="text-gray-500">Mode</span><span>{project.mode}</span></div>
          <div className="flex justify-between"><span className="text-gray-500">Evidence gates</span><span>{project.gates.filter(g => g.status === 'Complete' && g.evidence.trim()).length}/{project.gates.length}</span></div>
        </CardContent></Card>
      </aside>

      <main className="min-w-0 space-y-4">
        {tab === 'overview' && <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            <Metric label="Total project cost" value={money(metrics.totalCost)} note={`${money(metrics.costPerSf)} / SF`} />
            <Metric label="ARV" value={money(project.arv)} note={`${money(metrics.pricePerSf)} / SF`} />
            <Metric label="Net spec profit" value={money(metrics.saleProfit)} note={`${pct(metrics.saleMargin)} net margin`} bad={!metrics.salePass} />
            <Metric label="Rental DSCR" value={multiple(metrics.dscr)} note={`${money(metrics.annualCashFlow)} annual cash flow`} bad={!metrics.rentalPass} />
            <Metric label="Future equity need" value={money(Math.max(0, metrics.equityRequired + (project.mode === 'BTR' ? metrics.refinanceInjection : 0) - project.equityFunded))} note={`${money(headroom)} portfolio headroom`} bad={headroom < 0} />
          </div>
          <Section title="Portfolio register" subtitle="Illustrative records are not counted; every active project consumes capacity and liquidity." action={<Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={addProject}>Add</Button>}>
            <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b text-left text-xs uppercase text-gray-500"><th className="py-2">Project</th><th>Stage</th><th>Exit</th><th>Total cost</th><th>Spec margin</th><th>DSCR</th><th>Need</th></tr></thead>
              <tbody>{workspace.projects.map(item => { const result = calculateProject(item, settings); return <tr key={item.id} onClick={() => setActiveId(item.id)} className="cursor-pointer border-b hover:bg-gray-50"><td className="py-3 font-medium">{item.name}</td><td>{item.stage}</td><td>{recommendedExit(item, settings)}</td><td>{money(result.totalCost)}</td><td>{pct(result.saleMargin)}</td><td>{multiple(result.dscr)}</td><td>{money(Math.max(0, result.equityRequired - item.equityFunded))}</td></tr>; })}</tbody>
            </table></div>
          </Section>
          <Section title="Combined downside" subtitle={`Price and rent -${settings.stressPricePct}%; non-land costs +${settings.stressCostPct}%; rates +${settings.stressRatePoints} points; ${settings.stressDelayMonths}-month delay.`}>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Metric label="Stressed cost" value={money(stress.totalCost)} /><Metric label="Stressed profit" value={money(stress.saleProfit)} bad={stress.saleProfit < 0} /><Metric label="Stressed margin" value={pct(stress.saleMargin)} bad={!stress.salePass} /><Metric label="Stressed DSCR" value={multiple(stress.dscr)} bad={!stress.rentalPass} /></div>
          </Section>
        </>}

        {tab === 'spec' && <>
          <Section title="Opportunity and product" action={workspace.projects.length > 1 && <Button variant="danger" size="sm" icon={<Trash2 className="h-4 w-4" />} onClick={removeProject}>Remove</Button>}>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <Input label="Project name" value={project.name} onChange={e => updateProject({ name: e.target.value })} />
              <Input label="Address" value={project.address} onChange={e => updateProject({ address: e.target.value })} />
              <SelectField label="Stage" value={project.stage} options={['Screen','Diligence','Preconstruction','Construction','Sale / Lease-up','Closed','Stabilized','Pass']} onChange={value => updateProject({ stage: value as DevelopmentProject['stage'] })} />
              <SelectField label="Primary mode" value={project.mode} options={['Spec','BTR']} onChange={value => updateProject({ mode: value as DevelopmentProject['mode'] })} />
              <NumberField label="Finished SF" value={project.sf} onChange={sf => updateProject({ sf })} />
              <NumberField label="Units" value={project.units} onChange={units => updateProject({ units })} />
              <NumberField label="ARV" value={project.arv} onChange={arv => updateProject({ arv })} />
              <NumberField label="Sale price / SF" value={metrics.pricePerSf} step={.01} onChange={value => updateProject({ arv: value * project.sf })} />
            </div>
          </Section>
          <Section title="Spec exit economics" subtitle="Net margin includes construction financing, broker fees, closing costs, concessions and warranty reserve.">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Metric label="Net profit" value={money(metrics.saleProfit)} bad={!metrics.salePass} /><Metric label="Net sale margin" value={pct(metrics.saleMargin)} note={`${settings.minSaleMargin}% hurdle`} bad={!metrics.salePass} /><Metric label="Break-even price" value={money(metrics.breakEvenSale)} /><Metric label="Construction equity" value={money(metrics.equityRequired)} /></div>
            <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-6"><NumberField label="Build months" value={project.buildMonths} onChange={buildMonths => updateProject({ buildMonths })} /><NumberField label="Sale months" value={project.exitMonths} onChange={exitMonths => updateProject({ exitMonths })} /><NumberField label="Construction LTC" value={project.constructionLtc} onChange={constructionLtc => updateProject({ constructionLtc })} suffix="%" /><NumberField label="Construction LTV" value={project.constructionLtv} onChange={constructionLtv => updateProject({ constructionLtv })} suffix="%" /><NumberField label="Rate" value={project.constructionRate} step={.25} onChange={constructionRate => updateProject({ constructionRate })} suffix="%" /><NumberField label="Points" value={project.points} step={.25} onChange={points => updateProject({ points })} suffix="%" /></div>
            <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4"><NumberField label="Monthly carry" value={project.monthlyCarry} onChange={monthlyCarry => updateProject({ monthlyCarry })} /><NumberField label="Broker fee" value={project.brokerPct} step={.1} onChange={brokerPct => updateProject({ brokerPct })} suffix="%" /><NumberField label="Closing costs" value={project.saleClosingPct} step={.1} onChange={saleClosingPct => updateProject({ saleClosingPct })} suffix="%" /><NumberField label="Concessions" value={project.concessions} onChange={concessions => updateProject({ concessions })} /></div>
          </Section>
        </>}

        {tab === 'btr' && <>
          <Section title="Build-to-rent underwriting" subtitle="Permanent debt is the lowest amount supported by LTV, LTC and DSCR.">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Metric label="NOI" value={money(metrics.noi)} /><Metric label="Permanent loan" value={money(metrics.permanentLoan)} note={`${metrics.limitingConstraint} constrained`} /><Metric label="DSCR" value={multiple(metrics.dscr)} note={`${settings.minDscr.toFixed(2)}x hurdle`} bad={(metrics.dscr ?? 0) < settings.minDscr} /><Metric label="Cash-on-cash" value={pct(metrics.cashOnCash)} note={`${money(metrics.retainedEquity)} retained`} bad={(metrics.cashOnCash ?? 0) < settings.minCashOnCash} /></div>
            <div className="mt-4 grid gap-3 md:grid-cols-3 xl:grid-cols-6"><NumberField label="Monthly rent / unit" value={project.rentPerUnit} onChange={rentPerUnit => updateProject({ rentPerUnit })} /><NumberField label="Rent / SF" value={metrics.rentPerSf} step={.01} onChange={value => updateProject({ rentPerUnit: rentPerUnitFromSf(value, project.sf, project.units) })} /><NumberField label="Vacancy" value={project.vacancyPct} step={.1} onChange={vacancyPct => updateProject({ vacancyPct })} suffix="%" /><NumberField label="Management" value={project.managementPct} step={.1} onChange={managementPct => updateProject({ managementPct })} suffix="%" /><NumberField label="Repairs" value={project.repairsPct} step={.1} onChange={repairsPct => updateProject({ repairsPct })} suffix="%" /><NumberField label="Rental value" value={project.rentalValue} onChange={rentalValue => updateProject({ rentalValue })} /></div>
            <div className="mt-3 grid gap-3 md:grid-cols-3 xl:grid-cols-6"><NumberField label="Annual taxes" value={project.annualTaxes} onChange={annualTaxes => updateProject({ annualTaxes })} /><NumberField label="Insurance" value={project.annualInsurance} onChange={annualInsurance => updateProject({ annualInsurance })} /><NumberField label="Annual CapEx" value={project.annualCapex} onChange={annualCapex => updateProject({ annualCapex })} /><NumberField label="Permanent rate" value={project.permanentRate} step={.25} onChange={permanentRate => updateProject({ permanentRate })} suffix="%" /><NumberField label="Refi LTV" value={project.refinanceLtv} onChange={refinanceLtv => updateProject({ refinanceLtv })} suffix="%" /><NumberField label="Refi LTC" value={project.refinanceLtc} onChange={refinanceLtc => updateProject({ refinanceLtc })} suffix="%" /></div>
          </Section>
          <Section title="Refinance bridge"><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Metric label="Construction payoff" value={money(metrics.constructionLoan)} /><Metric label="Net permanent proceeds" value={money(metrics.permanentLoan * (1 - project.refinanceFeesPct / 100) - project.refinanceReserve)} /><Metric label="Cash injection at refi" value={money(metrics.refinanceInjection)} bad={metrics.refinanceInjection > 0} /><Metric label="Annual cash flow" value={money(metrics.annualCashFlow)} bad={metrics.annualCashFlow <= 0} /></div></Section>
        </>}

        {tab === 'costs' && <Section title="Budget, commitments and actuals" subtitle="Every category can be changed by total dollars or cost per square foot. Forecast is the greater of budget, committed, or incurred plus remaining.">
          <div className="mb-4 grid gap-3 sm:grid-cols-3"><Metric label="Total cost" value={money(metrics.totalCost)} note={`${money(metrics.costPerSf)} / SF`} /><Metric label="Cost to complete" value={money(metrics.costToComplete)} /><Metric label="Incurred but unpaid" value={money(metrics.unpaidCost)} bad={metrics.unpaidCost > 0} /></div>
          <div className="overflow-x-auto"><table className="w-full text-sm"><thead><tr className="border-b text-left text-xs uppercase text-gray-500"><th className="py-2">Cost code</th><th>Group</th><th>Budget</th><th>$/SF</th><th>Committed</th><th>Incurred</th><th>Paid</th><th>Remaining</th></tr></thead><tbody>{project.costs.map(row => editableCost(project, project.sf, row, updateCost))}</tbody></table></div>
        </Section>}

        {tab === 'delivery' && <Section title="Development stage gates" subtitle="A gate is complete only when the project team records the supporting evidence or document reference.">
          <div className="space-y-3">{project.gates.map(gate => <div key={gate.id} className="grid gap-2 rounded-lg border p-3 md:grid-cols-[2fr_1fr_150px_150px_2fr]">
            <Input aria-label="Gate title" value={gate.title} onChange={e => updateGate({ ...gate, title: e.target.value })} />
            <Input aria-label={`${gate.title} owner`} value={gate.owner} onChange={e => updateGate({ ...gate, owner: e.target.value })} />
            <SelectField label="Status" value={gate.status} options={['Open','In progress','Complete','Blocked']} onChange={status => updateGate({ ...gate, status: status as DevelopmentGate['status'] })} />
            <Input label="Due" type="date" value={gate.due} onChange={e => updateGate({ ...gate, due: e.target.value })} />
            <Input label="Evidence / document reference" value={gate.evidence} onChange={e => updateGate({ ...gate, evidence: e.target.value })} />
          </div>)}</div>
        </Section>}

        {tab === 'acquisitions' && <>
          <Section title="Wholesale lead → development conversion" subtitle="Link this underwriting to the originating wholesale lead; the lead remains in the main acquisition pipeline.">
            <div className="grid gap-3 md:grid-cols-3"><Input label="Source lead ID" value={project.leadId ?? ''} onChange={e => updateProject({ leadId: e.target.value })} /><Input label="Project address" value={project.address} onChange={e => updateProject({ address: e.target.value })} /><Input label="Target market" value={project.market} onChange={e => updateProject({ market: e.target.value })} /></div>
          </Section>
          <Section title="Investment committee routing"><div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">{[
            ['Develop', 'Clear an independently approved spec or rental case and every required diligence gate.'],
            ['Wholesale', 'Route non-core or capital-constrained opportunities to qualified buyers.'],
            ['Partner', 'Preserve upside when the deal works but liquidity, guarantees or execution capacity do not.'],
            ['Pass / nurture', 'Reprice, redesign or wait; never use the alternate exit to excuse a failed base case.'],
          ].map(([title, body]) => <div className="rounded-lg border p-4" key={title}><h3 className="font-semibold text-[#9D1C20]">{title}</h3><p className="mt-1 text-sm text-gray-600">{body}</p></div>)}</div></Section>
        </>}

        {tab === 'capital' && <>
          <Section title="Portfolio constraints"><div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6"><NumberField label="Unrestricted liquidity" value={settings.liquidity} onChange={liquidity => updateSettings({ liquidity })} /><NumberField label="Monthly overhead" value={settings.monthlyOverhead} onChange={monthlyOverhead => updateSettings({ monthlyOverhead })} /><NumberField label="Reserve months" value={settings.reserveMonths} onChange={reserveMonths => updateSettings({ reserveMonths })} /><NumberField label="Max specs" value={settings.maxSpecs} onChange={maxSpecs => updateSettings({ maxSpecs })} /><NumberField label="Max starts" value={settings.maxStarts} onChange={maxStarts => updateSettings({ maxStarts })} /><NumberField label="Equity funded" value={project.equityFunded} onChange={equityFunded => updateProject({ equityFunded })} /></div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><Metric label="Protected overhead" value={money(protectedReserve)} /><Metric label="Active development need" value={money(developmentNeed)} /><Metric label="Headroom before cash timing" value={money(headroom)} bad={headroom < 0} /><Metric label="Active starts" value={`${workspace.projects.filter(p => p.included && ['Preconstruction','Construction'].includes(p.stage)).length} / ${settings.maxStarts}`} /></div>
          </Section>
          <Section title="Downside policy"><div className="grid gap-3 md:grid-cols-4"><NumberField label="Price / rent decline" value={settings.stressPricePct} onChange={stressPricePct => updateSettings({ stressPricePct })} suffix="%" /><NumberField label="Non-land cost increase" value={settings.stressCostPct} onChange={stressCostPct => updateSettings({ stressCostPct })} suffix="%" /><NumberField label="Rate increase" value={settings.stressRatePoints} step={.25} onChange={stressRatePoints => updateSettings({ stressRatePoints })} suffix="pts" /><NumberField label="Delay" value={settings.stressDelayMonths} onChange={stressDelayMonths => updateSettings({ stressDelayMonths })} suffix="mo" /></div></Section>
          <Section title="13-week treasury" subtitle="Projected bank cash includes confirmed entries only. Enter all expected payments and receipts, including overhead and project draws. Unscheduled items are excluded; this is separate from lifetime project funding needs." action={<Button size="sm" onClick={() => { const item: CashItem = { id: crypto.randomUUID(), title: 'New cash item', week: 1, amount: 0, kind: 'Payment', confirmed: false }; mutate(current => ({ ...current, cash: [...current.cash, item] })); }} icon={<Plus className="h-4 w-4" />}>Cash item</Button>}>
            <div className="mb-4 grid gap-3 sm:grid-cols-3"><Metric label="Week 13 cash" value={money(treasury.closing)} bad={treasury.closing < protectedReserve} /><Metric label="Lowest projected cash" value={money(treasury.lowest)} bad={treasury.lowest < protectedReserve} /><Metric label="Minimum cash above reserve" value={money(treasury.lowest - protectedReserve)} bad={treasury.lowest < protectedReserve} /></div>
            <div className="mb-4 overflow-x-auto"><table className="w-full text-sm"><thead><tr><th>Week</th><th>Receipts</th><th>Payments</th><th>Closing cash</th></tr></thead><tbody>{treasury.weeks.map(week => <tr key={week.week} className="border-t text-center"><td>{week.week}</td><td>{money(week.receipts)}</td><td>{money(week.payments)}</td><td>{money(week.closing)}</td></tr>)}</tbody></table></div>
            <div className="space-y-2">{workspace.cash.map(item => <div key={item.id} className="grid gap-2 rounded border p-2 md:grid-cols-[2fr_90px_130px_1fr_120px_40px]">
              <Input aria-label="Cash item description" value={item.title} onChange={e => mutate(current => ({ ...current, cash: current.cash.map(row => row.id === item.id ? { ...row, title: e.target.value } : row) }))} />
              <input aria-label="Cash item week" type="number" min="1" max="13" value={item.week} onChange={e => mutate(current => ({ ...current, cash: current.cash.map(row => row.id === item.id ? { ...row, week: +e.target.value } : row) }))} className="rounded border px-2" />
              <select aria-label="Cash item direction" value={item.kind} onChange={e => mutate(current => ({ ...current, cash: current.cash.map(row => row.id === item.id ? { ...row, kind: e.target.value as CashItem['kind'] } : row) }))} className="rounded border px-2"><option>Receipt</option><option>Payment</option></select>
              <input aria-label="Cash item amount" type="number" value={item.amount} onChange={e => mutate(current => ({ ...current, cash: current.cash.map(row => row.id === item.id ? { ...row, amount: +e.target.value } : row) }))} className="rounded border px-2" />
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={item.confirmed} onChange={e => mutate(current => ({ ...current, cash: current.cash.map(row => row.id === item.id ? { ...row, confirmed: e.target.checked } : row) }))} />Confirmed</label>
              <button aria-label="Remove cash item" onClick={() => mutate(current => ({ ...current, cash: current.cash.filter(row => row.id !== item.id) }))}><Trash2 className="h-4 w-4 text-red-600" /></button>
            </div>)}</div>
          </Section>
        </>}

        {tab === 'plan' && <>
          <Section title="Hilltop operating thesis" subtitle="A locally focused capital-allocation company with one acquisition engine and independently accountable sale and rental exits.">
            <div className="grid gap-3 md:grid-cols-2">{[
              ['Spec discipline', 'Use repeatable infill plans, bounded finish palettes and nearby net sale evidence. Track concessions, absorption, total cost/SF and realized price/SF.'],
              ['BTR discipline', 'Design to rent per door and lifecycle cost. Confirm parcel-level density and utilities before assuming SFR, duplex or fourplex yield.'],
              ['Release discipline', 'No construction start before coordinated plans, permits, bid leveling, baseline schedule, lender process and funded equity are documented.'],
              ['Scale discipline', 'Prove acquisition, field execution and exit performance before adding starts, fixed overhead, fee builds or internal property management.'],
            ].map(([title, body]) => <div className="rounded-lg border p-4" key={title}><h3 className="font-semibold text-[#9D1C20]">{title}</h3><p className="mt-1 text-sm text-gray-600">{body}</p></div>)}</div>
          </Section>
          <Section title="Decision hurdles"><div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6"><NumberField label="Min net sale margin" value={settings.minSaleMargin} step={.5} onChange={minSaleMargin => updateSettings({ minSaleMargin })} suffix="%" /><NumberField label="Min DSCR" value={settings.minDscr} step={.05} onChange={minDscr => updateSettings({ minDscr })} suffix="x" /><NumberField label="Min cash-on-cash" value={settings.minCashOnCash} step={.5} onChange={minCashOnCash => updateSettings({ minCashOnCash })} suffix="%" /><NumberField label="Max retained equity" value={settings.maxRetainedEquity} onChange={maxRetainedEquity => updateSettings({ maxRetainedEquity })} /><SelectField label="Capital posture" value={settings.posture} options={['Cash generation','Balanced growth','Asset accumulation']} onChange={posture => updateSettings({ posture: posture as DevelopmentSettings['posture'] })} /></div></Section>
          <Section title="Living strategy and decisions"><textarea aria-label="Company strategy notes" rows={8} value={workspace.planNotes} onChange={e => mutate(current => ({ ...current, planNotes: e.target.value }))} className="w-full rounded-md border p-3 text-sm focus:border-[#9D1C20] focus:outline-none focus:ring-1 focus:ring-[#9D1C20]" /></Section>
        </>}

        {!metrics.salePass && !metrics.rentalPass && tab !== 'overview' && <div className="flex gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"><ShieldAlert className="h-5 w-5 shrink-0" /><div><strong>Neither exit currently clears Hilltop’s hurdles.</strong> Reduce basis or scope, improve verified revenue, restructure capital, partner, or pass. Do not approve the project on an unsupported alternate exit.</div></div>}
      </main>
    </div>
  </div>;
}
