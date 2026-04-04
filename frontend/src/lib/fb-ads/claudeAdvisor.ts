/**
 * Claude Advisor — all Anthropic API calls for the FB Ads Command Center.
 * Routes through the FastAPI backend at /api/ai/fb-ads/*
 */

export interface EnforcementResult {
  allowed: boolean;
  message: string;
  suggestions?: string[];
}

export interface PreFlightSummary {
  summary: string;
  estimated_cpl_cold: string;
  estimated_cpl_retargeting: string;
  recommendation: string;
}

export interface PerformanceAlert {
  type: 'urgent' | 'warning' | 'info';
  ad_set: string;
  message: string;
  recommendation: string;
}

export interface HeadlineReview {
  score: number;          // 0-100
  pain_point_present: boolean;
  local_signal_present: boolean;
  cta_present: boolean;
  emotional_hook_strength: 'strong' | 'moderate' | 'weak';
  generic_detected: boolean;
  flags: string[];
  suggestion?: string;
}

export interface CopyReview {
  pain_point_present: boolean;
  local_signal: boolean;
  cta_present: boolean;
  emotional_hook: 'strong' | 'moderate' | 'weak';
  generic_detected: boolean;
  flags: string[];
  score: number;
}

async function callApi<T>(endpoint: string, body: unknown): Promise<T> {
  const resp = await fetch(`/api/ai/fb-ads/${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(err || `API error ${resp.status}`);
  }
  return resp.json() as Promise<T>;
}

export const claudeAdvisor = {
  /** Review ad copy against battle plan standards */
  async reviewCopy(copy: string, segment: string): Promise<CopyReview> {
    return callApi<CopyReview>('review-copy', { copy, segment });
  },

  /** Review headline for compliance */
  async reviewHeadline(headline: string, segment: string): Promise<HeadlineReview> {
    return callApi<HeadlineReview>('review-headline', { headline, segment });
  },

  /** Generate pre-flight campaign summary */
  async preFlightSummary(wizardState: Record<string, unknown>): Promise<PreFlightSummary> {
    return callApi<PreFlightSummary>('preflight-summary', { wizard_state: wizardState });
  },

  /** Analyze performance data and return alerts */
  async analyzePerformance(performanceData: unknown[]): Promise<PerformanceAlert[]> {
    return callApi<PerformanceAlert[]>('performance-alerts', { performance_data: performanceData });
  },

  /** Compute battle plan compliance score for a live campaign */
  async scoreCampaign(campaign: unknown): Promise<{ score: number; flags: string[] }> {
    return callApi<{ score: number; flags: string[] }>('score-campaign', { campaign });
  },

  /** Explain a battle plan section in plain language */
  async explainSection(sectionTitle: string, content: string): Promise<string> {
    const result = await callApi<{ explanation: string }>('explain-section', {
      section_title: sectionTitle,
      content,
    });
    return result.explanation;
  },
};
