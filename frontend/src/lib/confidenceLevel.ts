export type ConfidenceLevel = 'high' | 'medium' | 'low';

const HIGH_MIN = 0.8;
const MEDIUM_MIN = 0.5;

/** Raw model confidence is never shown to staff: it is reduced to a word (`enums.confidence_level`). */
export function confidenceLevel(confidence: number): ConfidenceLevel {
  if (confidence >= HIGH_MIN) return 'high';
  return confidence >= MEDIUM_MIN ? 'medium' : 'low';
}
