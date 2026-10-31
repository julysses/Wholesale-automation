export type IntakeOrigin = {
  source_type: 'facebook_native_form' | 'retell_inbound' | 'online_offer_portal';
  inbound_integration_id: string | null;
  inbound_call_id: string | null;
  inbound_revision: number | null;
  portal_receipt_id?: string | null;
};
const uuid = (value: unknown) => typeof value === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(value);
export function validIntakeOrigin(row: IntakeOrigin): boolean {
  if (!row) return false;
  if (row.source_type === 'online_offer_portal') return uuid(row.portal_receipt_id) && row.inbound_integration_id === null && row.inbound_call_id === null && row.inbound_revision === null;
  if (row.portal_receipt_id != null) return false;
  if (row.source_type === 'facebook_native_form') return row.inbound_integration_id === null && row.inbound_call_id === null && row.inbound_revision === null;
  return row.source_type === 'retell_inbound' && uuid(row.inbound_integration_id)
    && typeof row.inbound_call_id === 'string' && /^[A-Za-z0-9_-]{1,200}$/.test(row.inbound_call_id)
    && Number.isInteger(row.inbound_revision) && row.inbound_revision! > 0 && row.inbound_revision! <= 1000000000;
}
export function intakeOriginLabel(row: IntakeOrigin): string {
  return row.source_type === 'retell_inbound' ? `Inbound call · revision ${row.inbound_revision}` : row.source_type === 'online_offer_portal' ? 'Online offer request' : 'Facebook inquiry';
}
