import { describe, expect, it } from 'vitest';
import { calculateProject, createProject, defaultSettings, payment, recommendedExit, createWorkspace, parseWorkspace, treasuryForecast, rentPerUnitFromSf } from '../src/lib/developmentEngine';

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


describe('development data and treasury', () => {
  it('rejects incomplete or malformed nested workspaces', () => {
    expect(() => parseWorkspace({ schema: 1, projects: [{}] })).toThrow();
    for (const corrupt of [
      (w: ReturnType<typeof createWorkspace>) => { w.projects[0].costs = [{}] as never; },
      (w: ReturnType<typeof createWorkspace>) => { w.settings = {} as never; },
      (w: ReturnType<typeof createWorkspace>) => { w.projects[0].gates[0].evidence = null as never; },
      (w: ReturnType<typeof createWorkspace>) => { w.projects[0].arv = Infinity; },
      (w: ReturnType<typeof createWorkspace>) => { w.cash = [{}] as never; },
    ]) {
      const workspace = createWorkspace(); corrupt(workspace);
      expect(() => parseWorkspace(workspace)).toThrow();
    }
    const valid = createWorkspace();
    expect(parseWorkspace(JSON.parse(JSON.stringify(valid)))).toEqual(valid);
  });

  it('round trips rent per square foot across all units', () => {
    const project = createProject();
    project.units = 4; project.sf = 4000; project.rentPerUnit = 2000;
    expect(calculateProject(project, defaultSettings).rentPerSf).toBe(2);
    expect(rentPerUnitFromSf(2, project.sf, project.units)).toBe(2000);
    expect(calculateProject(project, defaultSettings, true).rentPerSf).toBe(1.8);
  });

  it('tracks cash timing and excludes unconfirmed entries', () => {
    const workspace = createWorkspace();
    workspace.settings.liquidity = 500000;
    workspace.cash = [
      { id: 'a', title: 'Draw payment', week: 1, kind: 'Payment', amount: 450000, confirmed: true },
      { id: 'b', title: 'Loan receipt', week: 13, kind: 'Receipt', amount: 200000, confirmed: true },
      { id: 'c', title: 'Unconfirmed', week: 2, kind: 'Receipt', amount: 900000, confirmed: false },
    ];
    const forecast = treasuryForecast(workspace);
    expect(forecast.lowest).toBe(50000);
    expect(forecast.closing).toBe(250000);
    expect(forecast.weeks[0].closing).toBe(50000);
    expect(forecast.weeks[1].receipts).toBe(0);
  });
});
