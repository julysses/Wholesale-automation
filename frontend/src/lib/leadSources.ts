export const FACEBOOK_AD_SOURCE = 'facebook_ad';
export const FACEBOOK_AD_SOURCES = [FACEBOOK_AD_SOURCE, 'facebook_lead_ad'];

export function leadSourceLabel(source: string) {
  if (FACEBOOK_AD_SOURCES.includes(source)) return 'Facebook Ad';
  return source === 'web_form' ? 'Website Form' : source.replace(/_/g, ' ');
}
