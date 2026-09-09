import { describe, expect, it } from 'vitest';
import { calculateProject, createProject, defaultSettings, payment, recommendedExit } from '../src/lib/developmentEngine';

describe('development underwriting engine', () => {
  it('keeps editable category dollars and per-SF economics in sync', () => {
    const project = createProject();
    project.sf = 2_000;
    project.costs[0].budget = 100 * project.sf;
    project.costs[0].remaining = project.costs[0].budget;
    const result = calculateProject(project, defaultSettings);
    expect(project.costs[0].budget / project.sf).toBe(100);
    expect(result.costPerSf).toBeCloseTo(result.totalCost / 2_000);
    expect(result.pricePerSf).toBe(650);
  });

  it('constrains permanent debt by the lowest of LTV, LTC and DSCR', () => {
    const project = createProject();
    const result = calculateProject(project, defaultSettings);
    const ltv = result.rentalValue * project.refinanceLtv / 100;
    const ltc = result.totalCost * project.refinanceLtc / 100;
    const dscr = result.noi / defaultSettings.minDscr /
      (payment(1, project.permanentRate, project.amortizationYears) * 12);
    expect(result.permanentLoan).toBeCloseTo(Math.min(ltv, ltc, dscr));
  });

  it('does not use a weak rental case to approve a failed spec case', () => {
    const project = createProject();
    project.arv = 950_000;
    project.rentPerUnit = 2_000;
    expect(calculateProject(project, defaultSettings).salePass).toBe(false);
    expect(calculateProject(project, defaultSettings).rentalPass).toBe(false);
    expect(recommendedExit(project, defaultSettings)).toBe('Reprice, redesign, partner or pass');
  });

  it('handles zero-interest permanent debt', () => {
    expect(payment(120_000, 0, 10)).toBe(1_000);
  });
});
