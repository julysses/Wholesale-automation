import { expect, it } from 'vitest';
import { formatAcquisitionMetric } from '../src/lib/acquisitionMetric';
it('distinguishes currency, percentage and debt coverage without turning missing values into zero', () => {
  expect(formatAcquisitionMetric('profit', '40000')).toBe('$40,000.00');
  expect(formatAcquisitionMetric('profit_on_project_cost', '0.16')).toBe('16%');
  expect(formatAcquisitionMetric('debt_service_coverage', '1.25')).toBe('1.25×');
  expect(formatAcquisitionMetric('cashflow_annual', '-1500')).toBe('-$1,500.00');
  expect(formatAcquisitionMetric('profit', 0)).toBe('$0.00');
  expect(formatAcquisitionMetric('profit', null)).toBe('Unknown');
  expect(formatAcquisitionMetric('profit', 'NaN')).toBe('Unavailable');
  expect(formatAcquisitionMetric('future_metric', '0.16')).toBe('0.16');
});
