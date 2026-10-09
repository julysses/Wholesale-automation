export interface PublicIntakePayload {
  request_id: string;
  answers: Record<string, string>;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
}
export interface PendingPublicIntake {
  version: 1;
  formId: string;
  createdAt: string;
  answers: Record<string, string>;
  payload: PublicIntakePayload;
}
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export const publicIntakeKey = (formId: string) => `crm:pending-public-intake:${formId}:v1`;
export const UNCONFIRMED_INQUIRY = 'We could not confirm your inquiry. Your original answers are saved in this tab. Retry the saved inquiry, or contact our team before submitting another.';
function isAnswers(value: unknown): value is Record<string, string> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length <= 100
    && Object.entries(value).every(([key, answer]) => key.length <= 200 && typeof answer === 'string' && answer.length <= 5000);
}
export function readPublicIntake(storage: Pick<Storage, 'getItem'>, formId: string): PendingPublicIntake | null {
  const raw = storage.getItem(publicIntakeKey(formId));
  if (raw === null) return null;
  if (raw.length > 550000) throw new Error('Invalid saved inquiry');
  const draft = JSON.parse(raw);
  if (draft?.version !== 1 || draft.formId !== formId || typeof draft.createdAt !== 'string'
    || !Number.isFinite(Date.parse(draft.createdAt)) || !isAnswers(draft.answers)
    || !UUID.test(draft.payload?.request_id) || !isAnswers(draft.payload?.answers)
    || !['utm_source', 'utm_medium', 'utm_campaign'].every(key => draft.payload[key] === null
      || (typeof draft.payload[key] === 'string' && draft.payload[key].length <= 500))) {
    throw new Error('Invalid saved inquiry');
  }
  for (const [key, value] of Object.entries(draft.answers)) {
    if (draft.payload.answers[key] !== value) throw new Error('Saved answers do not match');
  }
  return draft;
}
export function preservePublicIntake(storage: Storage, draft: PendingPublicIntake): PendingPublicIntake {
  const key = publicIntakeKey(draft.formId);
  if (storage.getItem(key) !== null) throw new Error('An inquiry is already pending');
  const serialized = JSON.stringify(draft);
  // Validate before dispatch; read-back proves that recovery was actually stored.
  readPublicIntake({ getItem: () => serialized }, draft.formId);
  storage.setItem(key, serialized);
  if (storage.getItem(key) !== serialized) throw new Error('Inquiry recovery was not saved');
  return JSON.parse(serialized);
}
export function clearPublicIntake(storage: Storage, draft: PendingPublicIntake) {
  if (readPublicIntake(storage, draft.formId)?.payload.request_id !== draft.payload.request_id) {
    throw new Error('Saved inquiry changed');
  }
  storage.removeItem(publicIntakeKey(draft.formId));
  if (storage.getItem(publicIntakeKey(draft.formId)) !== null) throw new Error('Recovery cleanup failed');
}
export function matchesPublicIntakeReceipt(result: unknown, draft: PendingPublicIntake): boolean {
  if (!result || typeof result !== 'object') return false;
  const receipt = result as Record<string, unknown>;
  return receipt.success === true && receipt.submission_id === draft.payload.request_id && receipt.processing_status === 'processed';
}
