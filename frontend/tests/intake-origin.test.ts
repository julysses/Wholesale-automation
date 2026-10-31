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
it('requires a portal receipt and labels the offer request without granting another origin', () => {
  const portal: IntakeOrigin = { ...facebook, source_type: 'online_offer_portal', portal_receipt_id: 'fd000000-0000-4000-8000-000000000001' };
  expect(validIntakeOrigin(portal)).toBe(true);
  expect(intakeOriginLabel(portal)).toBe('Online offer request');
  expect(validIntakeOrigin({ ...portal, portal_receipt_id: undefined })).toBe(false);
  expect(validIntakeOrigin({ ...portal, inbound_call_id: 'call' })).toBe(false);
  expect(validIntakeOrigin({ ...facebook, portal_receipt_id: portal.portal_receipt_id })).toBe(false);
});
