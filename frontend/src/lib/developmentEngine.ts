export type ProjectMode = 'Spec' | 'BTR';
export type ProjectStage = 'Screen' | 'Diligence' | 'Preconstruction' | 'Construction' | 'Sale / Lease-up' | 'Closed' | 'Stabilized' | 'Pass';
export type CostGroup = 'Land' | 'Hard' | 'Soft' | 'Contingency';

export interface DevelopmentCost {
  id: string;
  name: string;
  group: CostGroup;
  budget: number;
  committed: number;
  incurred: number;
  paid: number;
  remaining: number;
}

export interface DevelopmentGate {
  id: string;
  title: string;
  owner: string;
  status: 'Open' | 'In progress' | 'Complete' | 'Blocked';
  due: string;
  evidence: string;
}

export interface DevelopmentProject {
  id: string;
  leadId?: string;
  name: string;
  address: string;
  market: string;
  mode: ProjectMode;
  stage: ProjectStage;
  included: boolean;
  sf: number;
  units: number;
  arv: number;
  buildMonths: number;
  exitMonths: number;
  constructionLtc: number;
  constructionLtv: number;
  constructionRate: number;
  points: number;
  monthlyCarry: number;
  brokerPct: number;
  saleClosingPct: number;
  concessions: number;
  warranty: number;
  rentPerUnit: number;
  otherMonthlyIncome: number;
  vacancyPct: number;
  managementPct: number;
  repairsPct: number;
  annualTaxes: number;
  annualInsurance: number;
  annualHoa: number;
  annualUtilities: number;
  annualTurnover: number;
  annualCapex: number;
  permanentRate: number;
  amortizationYears: number;
  refinanceLtv: number;
  refinanceLtc: number;
  refinanceFeesPct: number;
  refinanceReserve: number;
  rentalValue: number;
  capRate: number;
  equityFunded: number;
  startMonth: number;
  costs: DevelopmentCost[];
  gates: DevelopmentGate[];
  notes: string;
}

export interface DevelopmentSettings {
  liquidity: number;
  monthlyOverhead: number;
  reserveMonths: number;
  maxSpecs: number;
  maxStarts: number;
  minSaleMargin: number;
  minDscr: number;
  minCashOnCash: number;
  maxRetainedEquity: number;
  stressPricePct: number;
  stressCostPct: number;
  stressRatePoints: number;
  stressDelayMonths: number;
  posture: 'Cash generation' | 'Balanced growth' | 'Asset accumulation';
}

export interface CashItem {
  id: string;
  title: string;
  week: number;
  amount: number;
  kind: 'Receipt' | 'Payment';
  confirmed: boolean;
}

export interface DevelopmentWorkspace {
  schema: 1;
  settings: DevelopmentSettings;
  projects: DevelopmentProject[];
  cash: CashItem[];
  planNotes: string;
}

export interface DevelopmentMetrics {
  totalCost: number;
  baseCost: number;
  financeCost: number;
  constructionLoan: number;
  equityRequired: number;
  saleProfit: number;
  saleMargin: number;
  breakEvenSale: number;
  noi: number;
  rentalValue: number;
  permanentLoan: number;
  debtService: number;
  dscr: number | null;
  annualCashFlow: number;
  cashOnCash: number | null;
  retainedEquity: number;
  refinanceInjection: number;
  costPerSf: number;
  pricePerSf: number;
  rentPerSf: number;
  costToComplete: number;
  unpaidCost: number;
  salePass: boolean;
  rentalPass: boolean;
  limitingConstraint: 'LTV' | 'LTC' | 'DSCR';
}

const id = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;

const COST_TEMPLATE: Array<[string, string, CostGroup, number]> = [
  ['land', 'Land purchase', 'Land', 275_000],
  ['closing', 'Acquisition & title', 'Land', 10_000],
  ['site', 'Demo, sitework & utilities', 'Hard', 65_000],
  ['foundation', 'Foundation & slab', 'Hard', 80_000],
  ['frame', 'Framing & structure', 'Hard', 135_000],
  ['envelope', 'Roof, windows & envelope', 'Hard', 100_000],
  ['mep', 'Mechanical, electrical & plumbing', 'Hard', 110_000],
  ['interior', 'Insulation, drywall & paint', 'Hard', 65_000],
  ['finish', 'Cabinets, fixtures & finishes', 'Hard', 85_000],
  ['landscape', 'Exterior & landscape', 'Hard', 40_000],
  ['design', 'Architecture, engineering & survey', 'Soft', 30_000],
  ['permits', 'Permits, fees & testing', 'Soft', 20_000],
  ['gc', 'GC / owner-builder supervision', 'Soft', 35_000],
  ['contingency', 'Unallocated contingency', 'Contingency', 20_000],
];

const GATE_TEMPLATE: Array<[string, string]> = [
  ['Title, survey, easements & restrictions', 'Acquisitions'],
  ['Zoning, setbacks, height & density verified', 'Development'],
  ['Soils, drainage, floodplain & utilities verified', 'Civil / engineer'],
  ['Sold, active, tract & rental comps verified', 'Acquisitions'],
  ['Plans, specifications, trade bids & schedule aligned', 'Project manager'],
  ['Construction term sheet & equity secured', 'Principal'],
  ['Independent exit and downside review', 'Principal'],
];

export const defaultSettings: DevelopmentSettings = {
  liquidity: 500_000,
  monthlyOverhead: 7_500,
  reserveMonths: 12,
  maxSpecs: 2,
  maxStarts: 2,
  minSaleMargin: 22,
  minDscr: 1.25,
  minCashOnCash: 6,
  maxRetainedEquity: 200_000,
  stressPricePct: 10,
  stressCostPct: 10,
  stressRatePoints: 2,
  stressDelayMonths: 3,
  posture: 'Balanced growth',
};

export function createProject(name = 'New development opportunity'): DevelopmentProject {
  return {
    id: id(), name, address: '', market: 'DFW infill', mode: 'Spec', stage: 'Screen', included: true,
    sf: 2_800, units: 1, arv: 1_300_000, buildMonths: 11, exitMonths: 3,
    constructionLtc: 70, constructionLtv: 65, constructionRate: 10, points: 2, monthlyCarry: 1_800,
    brokerPct: 5, saleClosingPct: 1, concessions: 15_000, warranty: 6_500,
    rentPerUnit: 6_500, otherMonthlyIncome: 0, vacancyPct: 5, managementPct: 8, repairsPct: 4,
    annualTaxes: 25_000, annualInsurance: 4_500, annualHoa: 0, annualUtilities: 600,
    annualTurnover: 1_200, annualCapex: 2_000, permanentRate: 8, amortizationYears: 30,
    refinanceLtv: 75, refinanceLtc: 75, refinanceFeesPct: 2, refinanceReserve: 10_000,
    rentalValue: 1_300_000, capRate: 5.5, equityFunded: 0, startMonth: 0,
    costs: COST_TEMPLATE.map(([costId, costName, group, budget]) => ({
      id: costId, name: costName, group, budget, committed: 0, incurred: 0, paid: 0, remaining: budget,
    })),
    gates: GATE_TEMPLATE.map(([title, owner]) => ({ id: id(), title, owner, status: 'Open', due: '', evidence: '' })),
    notes: '',
  };
}

export function createWorkspace(): DevelopmentWorkspace {
  return { schema: 1, settings: { ...defaultSettings }, projects: [createProject()], cash: [], planNotes: '' };
}

export function payment(principal: number, annualRate: number, years: number): number {
  if (principal <= 0) return 0;
  const periods = Math.max(1, years * 12);
  const rate = annualRate / 1200;
  return rate === 0 ? principal / periods : principal * rate / (1 - (1 + rate) ** -periods);
}

export function calculateProject(project: DevelopmentProject, settings: DevelopmentSettings, stressed = false): DevelopmentMetrics {
  const priceFactor = 1 - (stressed ? settings.stressPricePct : 0) / 100;
  const costFactor = 1 + (stressed ? settings.stressCostPct : 0) / 100;
  const rateAdd = stressed ? settings.stressRatePoints : 0;
  const delay = stressed ? settings.stressDelayMonths : 0;

  const rows = project.costs.map(cost => {
    const forecast = Math.max(cost.budget, cost.committed, cost.incurred + Math.max(0, cost.remaining));
    return { ...cost, forecast: forecast * (cost.group === 'Land' ? 1 : costFactor) };
  });
  const baseCost = rows.reduce((sum, row) => sum + row.forecast, 0);
  const stressedArv = project.arv * priceFactor;
  const constructionLoan = Math.max(0, Math.min(
    baseCost * project.constructionLtc / 100,
    stressedArv * project.constructionLtv / 100,
  ));
  const duration = project.buildMonths + project.exitMonths + delay;
  const averageBalance = constructionLoan * .55;
  const interest = averageBalance * (project.constructionRate + rateAdd) / 100 * duration / 12;
  const financeCost = interest + constructionLoan * project.points / 100 + project.monthlyCarry * (duration + 1);
  const totalCost = baseCost + financeCost;
  const sellingCost = stressedArv * (project.brokerPct + project.saleClosingPct) / 100 + project.concessions + project.warranty;
  const saleProfit = stressedArv - totalCost - sellingCost;
  const saleMargin = stressedArv > 0 ? saleProfit / stressedArv * 100 : 0;
  const breakEvenSale = (totalCost + project.concessions + project.warranty) /
    Math.max(.01, 1 - (project.brokerPct + project.saleClosingPct) / 100);
  const equityRequired = Math.max(0, totalCost - constructionLoan);

  const grossRent = project.rentPerUnit * project.units * 12 * priceFactor;
  const effectiveIncome = grossRent * (1 - project.vacancyPct / 100) + project.otherMonthlyIncome * 12;
  const variableExpenses = effectiveIncome * (project.managementPct + project.repairsPct) / 100;
  const fixedExpenses = project.annualTaxes + project.annualInsurance + project.annualHoa + project.annualUtilities + project.annualTurnover;
  const noi = effectiveIncome - variableExpenses - fixedExpenses;
  const incomeValue = noi > 0 ? noi / (project.capRate / 100) : 0;
  const rentalValue = Math.min(project.rentalValue * priceFactor, incomeValue || Number.POSITIVE_INFINITY);
  const annualPaymentPerDollar = payment(1, project.permanentRate + rateAdd, project.amortizationYears) * 12;
  const ltvLoan = rentalValue * project.refinanceLtv / 100;
  const ltcLoan = totalCost * project.refinanceLtc / 100;
  const dscrLoan = annualPaymentPerDollar > 0 ? Math.max(0, noi / settings.minDscr / annualPaymentPerDollar) : 0;
  const permanentLoan = Math.max(0, Math.min(ltvLoan, ltcLoan, dscrLoan));
  const limitingConstraint: DevelopmentMetrics['limitingConstraint'] =
    permanentLoan === dscrLoan ? 'DSCR' : permanentLoan === ltvLoan ? 'LTV' : 'LTC';
  const debtService = payment(permanentLoan, project.permanentRate + rateAdd, project.amortizationYears) * 12;
  const annualCashFlow = noi - project.annualCapex - debtService;
  const netRefinance = permanentLoan * (1 - project.refinanceFeesPct / 100) - project.refinanceReserve;
  const refinanceInjection = Math.max(0, constructionLoan - netRefinance);
  const refinanceDistribution = Math.max(0, netRefinance - constructionLoan);
  const retainedEquity = Math.max(0, equityRequired + refinanceInjection - refinanceDistribution);
  const dscr = debtService > 0 ? noi / debtService : null;
  const cashOnCash = retainedEquity > 0 ? annualCashFlow / retainedEquity * 100 : null;

  return {
    totalCost, baseCost, financeCost, constructionLoan, equityRequired,
    saleProfit, saleMargin, breakEvenSale, noi, rentalValue, permanentLoan, debtService, dscr,
    annualCashFlow, cashOnCash, retainedEquity, refinanceInjection,
    costPerSf: project.sf > 0 ? totalCost / project.sf : 0,
    pricePerSf: project.sf > 0 ? stressedArv / project.sf : 0,
    rentPerSf: project.sf > 0 ? project.rentPerUnit * project.units * priceFactor / project.sf : 0,
    costToComplete: rows.reduce((sum, row) => sum + Math.max(0, row.forecast - row.incurred), 0),
    unpaidCost: rows.reduce((sum, row) => sum + Math.max(0, row.incurred - row.paid), 0),
    salePass: saleMargin >= settings.minSaleMargin,
    rentalPass: noi > 0 && annualCashFlow > 0 && permanentLoan > 0 && (dscr ?? 0) >= settings.minDscr &&
      (cashOnCash === null || cashOnCash >= settings.minCashOnCash) && retainedEquity <= settings.maxRetainedEquity,
    limitingConstraint,
  };
}

export function recommendedExit(project: DevelopmentProject, settings: DevelopmentSettings): string {
  const metrics = calculateProject(project, settings);
  if (metrics.salePass && metrics.rentalPass) {
    if (settings.posture === 'Cash generation') return 'Sell — both exits qualify';
    if (settings.posture === 'Asset accumulation') return 'Hold — both exits qualify';
    return 'Dual exit — principal decision';
  }
  if (metrics.salePass) return 'Spec exit only';
  if (metrics.rentalPass) return 'Rental exit only';
  return 'Reprice, redesign, partner or pass';
}

export function portfolioEquityNeed(workspace: DevelopmentWorkspace): number {
  return workspace.projects
    .filter(project => project.included && !['Closed', 'Stabilized', 'Pass'].includes(project.stage))
    .reduce((sum, project) => {
      const metrics = calculateProject(project, workspace.settings);
      return sum + Math.max(0, metrics.equityRequired + (project.mode === 'BTR' ? metrics.refinanceInjection : 0) - project.equityFunded);
    }, 0);
}

export function workspaceStorageKey(userId: string): string {
  if (!userId) throw new Error('Operator ID is required');
  return `hilltop-development-workspace-v1:${userId}`;
}

// Validate all required fields before using local, cloud, or imported data.
export function parseWorkspace(value: unknown): DevelopmentWorkspace {
  const invalid = () => { throw new Error('Invalid development workspace'); };
  const shape = (input: unknown, template: unknown): void => {
    if (Array.isArray(template)) {
      if (!Array.isArray(input)) return invalid();
      input.forEach(item => shape(item, template[0]));
    } else if (template !== null && typeof template === 'object') {
      if (!input || typeof input !== 'object' || Array.isArray(input)) return invalid();
      for (const [key, sample] of Object.entries(template)) shape((input as Record<string, unknown>)[key], sample);
    } else if (typeof input !== typeof template || (typeof input === 'number' && !Number.isFinite(input))) invalid();
  };
  const template = createWorkspace();
  template.cash = [{ id: '', title: '', week: 1, amount: 0, kind: 'Payment', confirmed: false }];
  shape(value, template);
  const workspace = value as DevelopmentWorkspace;
  if (workspace.schema !== 1 || !workspace.projects.length) invalid();
  const uniqueIds = (rows: { id: string }[]) => {
    if (rows.some(row => !row.id) || new Set(rows.map(row => row.id)).size !== rows.length) invalid();
  };
  uniqueIds(workspace.projects); uniqueIds(workspace.cash);
  if (!['Cash generation', 'Balanced growth', 'Asset accumulation'].includes(workspace.settings.posture)) invalid();
  for (const project of workspace.projects) {
    if (!['Spec', 'BTR'].includes(project.mode) || !['Screen', 'Diligence', 'Preconstruction', 'Construction', 'Sale / Lease-up', 'Closed', 'Stabilized', 'Pass'].includes(project.stage)) invalid();
    if (project.leadId !== undefined && typeof project.leadId !== 'string') invalid();
    if (project.sf <= 0 || project.units < 1 || !Number.isInteger(project.units) || !project.costs.length) invalid();
    uniqueIds(project.costs); uniqueIds(project.gates);
    if (project.costs.some(row => !['Land', 'Hard', 'Soft', 'Contingency'].includes(row.group))) invalid();
    if (project.gates.some(row => !['Open', 'In progress', 'Complete', 'Blocked'].includes(row.status))) invalid();
  }
  if (workspace.cash.some(row => !['Receipt', 'Payment'].includes(row.kind) || !Number.isInteger(row.week) || row.week < 1 || row.week > 13 || row.amount < 0)) invalid();
  return workspace;
}

export function rentPerUnitFromSf(rentPerSf: number, sf: number, units: number): number {
  return units > 0 ? rentPerSf * sf / units : 0;
}

export function treasuryForecast(workspace: DevelopmentWorkspace) {
  let closing = workspace.settings.liquidity;
  let lowest = closing;
  const weeks = Array.from({ length: 13 }, (_, index) => {
    const items = workspace.cash.filter(item => item.confirmed && item.week === index + 1);
    const receipts = items.filter(item => item.kind === 'Receipt').reduce((sum, item) => sum + item.amount, 0);
    const payments = items.filter(item => item.kind === 'Payment').reduce((sum, item) => sum + item.amount, 0);
    closing += receipts - payments;
    lowest = Math.min(lowest, closing);
    return { week: index + 1, receipts, payments, closing };
  });
  return { weeks, closing, lowest };
}
