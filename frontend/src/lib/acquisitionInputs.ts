export type Strategy = 'fix_and_flip' | 'rental' | 'development' | 'wholesale';
export type CaseName = 'base' | 'downside' | 'upside';
export type Entry = { value: string; source: string; basis: 'estimate' | 'source_reported'; confidence: 'low' | 'medium' | 'high'; as_of: string };
export type Draft = Record<CaseName, Record<string, Entry>>;
export const caseNames: CaseName[] = ['base', 'downside', 'upside'];
export const strategyNames: Record<Strategy, string> = { fix_and_flip: 'Fix and flip', rental: 'Rental', development: 'Development', wholesale: 'Wholesale assignment' };
const common = ['purchase_price','acquisition_closing','liens','holding_months','holding_monthly_ex_interest','financing.principal','financing.average_balance','financing.annual_rate','financing.points_rate','financing.other_fees','offer_floor_fraction'];
const specific: Record<Strategy, string[]> = {
  fix_and_flip: ['arv','repairs','contingency','selling_rate','selling_fixed','target_profit'],
  development: ['completed_value','hard_costs','soft_costs','infrastructure','permits','contingency','selling_rate','selling_fixed','target_profit'],
  rental: ['market_value','repairs','contingency','monthly_rent','vacancy_rate','property_tax_annual','insurance_annual','maintenance_annual','utilities_annual','hoa_annual','other_operating_annual','management_rate','capital_reserve_annual','amortization_months','target_cap_rate','target_cash_on_cash'],
  wholesale: ['contract_price','end_buyer_price','assignment_expenses','target_net_fee','offer_floor_fraction'],
};
export function inputPaths(strategy: Strategy, buyer: Exclude<Strategy,'wholesale'>): string[] {
  return strategy === 'wholesale' ? [...specific.wholesale, ...inputPaths(buyer,buyer).map(p => 'buyer_case.'+p)] : [...common,...specific[strategy]];
}
export function fieldUnit(path: string): 'USD' | 'fraction' | 'months' | 'integer months' {
  if (path.endsWith('amortization_months')) return 'integer months';
  if (path.endsWith('holding_months')) return 'months';
  if (path.includes('rate') || path.endsWith('offer_floor_fraction') || path.endsWith('target_cash_on_cash')) return 'fraction';
  return 'USD';
}
export const emptyEntry = (): Entry => ({ value:'',source:'',basis:'estimate',confidence:'low',as_of:'' });
export const emptyDraft = (): Draft => ({ base:{},downside:{},upside:{} });
export const fieldLabel = (path: string) => path.replace('buyer_case.','End buyer: ').replace('financing.','Financing: ').replaceAll('_',' ').replace(/^arv$/, 'After-repair value');
export function buildInputs(strategy: Strategy, buyer: Exclude<Strategy,'wholesale'>, draft: Draft, uncertainties: string[]) {
  const cases: Record<string, Record<string, unknown>> = {};
  for (const name of caseNames) {
    const result: Record<string, unknown> = { strategy };
    if (strategy === 'wholesale') result.buyer_case = { strategy: buyer };
    for (const path of inputPaths(strategy,buyer)) {
      const entry = draft[name][path];
      if (!entry || !entry.value.trim()) continue; // Missing is never converted to zero.
      const unit = fieldUnit(path); const value = entry.value.trim(); const number = Number(value);
      const precision = unit === 'fraction' ? 8 : unit === 'months' ? 4 : unit === 'integer months' ? 0 : 2;
      const pattern = precision ? new RegExp(`^\\d+(?:\\.\\d{1,${precision}})?$`) : /^\d+$/;
      if (!pattern.test(value) || !Number.isFinite(number) || number < 0 || number > (unit === 'fraction' ? 1 : unit.includes('months') ? 600 : 1e12)) throw new Error(`${name}: ${fieldLabel(path)} has an invalid ${unit} value.`);
      if ((path.endsWith('target_cap_rate') || path.endsWith('target_cash_on_cash')) && number === 0) throw new Error(`${name}: target return must be greater than zero.`);
      if (unit === 'integer months' && number > 0 && number < 12) throw new Error(`${name}: amortization must be zero (interest-only) or at least 12 months.`);
      if (unit !== 'integer months' && !entry.source.trim()) throw new Error(`${name}: add a source for ${fieldLabel(path)}.`);
      let parent = result; const keys = path.split('.');
      for (const key of keys.slice(0,-1)) { parent[key] ??= {}; parent = parent[key] as Record<string,unknown>; }
      parent[keys[keys.length-1]] = unit === 'integer months' ? number : { value, source:entry.source.trim(), basis:entry.basis, confidence:entry.confidence, as_of:entry.as_of || null };
    }
    cases[name] = result;
  }
  return { cases, uncertainties };
}
