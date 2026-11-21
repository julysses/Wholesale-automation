export const FACEBOOK_AD_SOURCE = 'facebook_ad';
export const FACEBOOK_AD_SOURCES = [FACEBOOK_AD_SOURCE, 'facebook_lead_ad'];

export function leadSourceLabel(source: string) {
  return FACEBOOK_AD_SOURCES.includes(source) ? 'Facebook Ad' : source.replace(/_/g, ' ');
}
