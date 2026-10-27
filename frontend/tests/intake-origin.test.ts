import { expect, it } from 'vitest';
import { type IntakeOrigin, validIntakeOrigin, intakeOriginLabel } from '../src/lib/intakeOrigin';
const facebook: IntakeOrigin = { source_type: 'facebook_native_form', inbound_integration_id: null, inbound_call_id: null, inbound_revision: null };
const inbound: IntakeOrigin = { source_type: 'retell_inbound', inbound_integration_id: '96000000-0000-4000-8000-000000000001', inbound_call_id: 'call_test', inbound_revision: 2 };
it('labels only valid source-specific origins', () => {
  expect(validIntakeOrigin(facebook)).toBe(true); expect(validIntakeOrigin(inbound)).toBe(true);
  expect(intakeOriginLabel(inbound)).toBe('Inbound call · revision 2');
  expect(intakeOriginLabel(facebook)).toBe('Facebook inquiry');
});
it.each([{ ...inbound, inbound_revision: 0 }, { ...inbound, inbound_revision: 1.5 }, { ...inbound, inbound_revision: 1000000001 },
  { ...inbound, inbound_integration_id: null }, { ...inbound, inbound_call_id: '' }, { ...facebook, inbound_revision: 1 },
  { ...facebook, source_type: 'unknown' }, {}])('rejects malformed or mixed origin %j', value => {
  expect(validIntakeOrigin(value as IntakeOrigin)).toBe(false);
});
