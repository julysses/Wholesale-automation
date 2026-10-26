import { apiFetch } from '@/lib/api';
type Assessment = { classification: string; reason_codes: string[]; missing_fields: string[]; policy_version: string;
  canonical_county: string | null; canonical_state: string | null; identity_link_current: boolean; target_lead_id?: string;
  ownership_verified: false; outreach_authorized: false; binding_offer: false; contact_permission_granted: false };
export type Saved = { id: string; sequence: number; classification: string; created_at: string; assessment: Assessment };
type State = { assessment: Assessment; evidence_hash: string; sequence: number; latest_assessment: Saved | null; assessment_current: boolean };
export const classifications = ['qualified', 'incomplete', 'duplicate', 'unqualified', 'requires_human_review'];
function validAssessment(value: Assessment) {
  return value && classifications.includes(value.classification) && typeof value.policy_version === 'string'
    && Array.isArray(value.reason_codes) && value.reason_codes.every(code => typeof code === 'string')
    && Array.isArray(value.missing_fields) && value.missing_fields.every(field => typeof field === 'string')
    && (value.canonical_county === null || typeof value.canonical_county === 'string')
    && (value.canonical_state === null || typeof value.canonical_state === 'string')
    && typeof value.identity_link_current === 'boolean' && value.ownership_verified === false && value.outreach_authorized === false
    && value.binding_offer === false && value.contact_permission_granted === false;
}
export function validSaved(value: Saved) {
  return value && typeof value.id === 'string' && Number.isInteger(value.sequence) && value.sequence > 0
    && typeof value.created_at === 'string' && classifications.includes(value.classification)
    && validAssessment(value.assessment) && value.classification === value.assessment.classification;
}
export async function loadQualification(path: string, signal?: AbortSignal): Promise<State> {
  const data = await (await apiFetch(path, { signal })).json();
  if (!validAssessment(data?.assessment) || !/^[a-f0-9]{64}$/.test(data.evidence_hash) || !Number.isInteger(data.sequence)
    || data.sequence < 0 || typeof data.assessment_current !== 'boolean'
    || (data.latest_assessment !== null && !validSaved(data.latest_assessment)) || (data.assessment_current && data.latest_assessment === null))
    throw new Error('Invalid qualification response');
  return data;
}

