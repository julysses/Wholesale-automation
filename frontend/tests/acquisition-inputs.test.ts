import { expect, it } from 'vitest';
import { buildInputs, emptyDraft, emptyEntry, inputPaths } from '../src/lib/acquisitionInputs';
it('preserves missing values, explicit sourced zero, independent cases and original decimals',()=>{
  const draft=emptyDraft();draft.base.repairs={...emptyEntry(),value:'0.00',source:'Reviewed contractor quote'};
  const result=buildInputs('fix_and_flip','fix_and_flip',draft,['repairs']);
  expect(result.cases.base.repairs).toEqual({value:'0.00',source:'Reviewed contractor quote',basis:'estimate',confidence:'low',as_of:null});
  expect(result.cases.downside.repairs).toBeUndefined();expect(result.cases.upside.repairs).toBeUndefined();
});
it('rejects untraceable and invalid numeric assumptions before a request',()=>{
  const draft=emptyDraft();draft.base.repairs={...emptyEntry(),value:'100'};
  expect(()=>buildInputs('fix_and_flip','fix_and_flip',draft,[])).toThrow('add a source');
  for(const value of ['NaN','-1','1e6','12.345']){draft.base.repairs={...emptyEntry(),value,source:'Fixture'};expect(()=>buildInputs('fix_and_flip','fix_and_flip',draft,[])).toThrow('invalid');}
});
it('builds independent buyer economics and fractional rate evidence without default amounts',()=>{
  const draft=emptyDraft();draft.base['buyer_case.financing.annual_rate']={...emptyEntry(),value:'0.08',source:'Term sheet'};
  const result=buildInputs('wholesale','rental',draft,[]);
  expect(result.cases.base.buyer_case).toEqual({strategy:'rental',financing:{annual_rate:{value:'0.08',source:'Term sheet',basis:'estimate',confidence:'low',as_of:null}}});
  expect(inputPaths('development','rental')).toContain('infrastructure');
  expect(inputPaths('rental','rental')).toContain('capital_reserve_annual');
});
