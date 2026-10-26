// Units come from acquisition-underwriting-v1, never from a value's magnitude.
const percentages = new Set(['profit_on_project_cost', 'profit_on_net_cash', 'profit_margin', 'cap_rate_on_cost', 'cash_on_cash']);
const currencies = new Set(['exit_value', 'total_project_cost', 'profit', 'net_project_cash_required', 'gross_rent_annual',
  'effective_rent_annual', 'noi_annual', 'capital_reserve_annual', 'debt_service_annual', 'cashflow_annual', 'total_project_basis',
  'equity_at_market_value', 'cap_rate_ceiling', 'cash_on_cash_ceiling', 'market_value_ceiling', 'gross_assignment_spread',
  'net_assignment_proceeds', 'buyer_supported_price']);
export function formatAcquisitionMetric(key: string, value: unknown): string {
  if (value === null || value === undefined || value === '') return 'Unknown';
  if (typeof value !== 'number' && typeof value !== 'string') return 'Unavailable';
  const number = Number(value);
  if (!Number.isFinite(number)) return 'Unavailable';
  if (percentages.has(key)) return new Intl.NumberFormat('en-US', { style: 'percent', maximumFractionDigits: 2 }).format(number);
  if (currencies.has(key)) return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(number);
  if (key === 'debt_service_coverage') return `${number.toFixed(2)}×`;
  return String(value); // Unknown metrics retain their original representation, without an invented unit.
}
