import type { DetectedBy } from '@/api/types';

export type HitSource = 'dictionary' | 'ai_hypothesis' | 'confirmed' | 'rejected';

/**
 * How a phrase hit is presented (D18): a dictionary match is a rule-based fact, an LLM match is only a
 * hypothesis until an analyst accepts it, and the analyst's decision wins over both.
 */
export function hitSource(hit: { detected_by: DetectedBy; confirmed: boolean | null }): HitSource {
  if (hit.confirmed === false) return 'rejected';
  if (hit.confirmed === true) return 'confirmed';
  return hit.detected_by === 'llm' ? 'ai_hypothesis' : 'dictionary';
}
