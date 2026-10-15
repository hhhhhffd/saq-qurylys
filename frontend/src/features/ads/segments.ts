export interface HitRange {
  /** character offset into the text (JS string index) */
  start: number;
  /** exclusive end offset */
  end: number;
}

export interface TextSegment<H extends HitRange> {
  text: string;
  /** null for plain text between hits */
  hit: H | null;
}

export type HitState = 'confirmed' | 'rejected' | 'unreviewed';

export function hitState(hit: { confirmed: boolean | null }): HitState {
  if (hit.confirmed === true) return 'confirmed';
  if (hit.confirmed === false) return 'rejected';
  return 'unreviewed';
}

/**
 * Splits `text` into plain and highlighted segments.
 * Offsets are clamped to the text; empty, inverted or non-finite ranges are dropped.
 * Overlaps are resolved by start position (longer range first on a tie): a range
 * fully covered by an earlier one is skipped, a partly covered one is trimmed.
 */
export function buildSegments<H extends HitRange>(text: string, hits: readonly H[]): TextSegment<H>[] {
  const ranges = hits
    .map((hit) => ({ hit, start: Math.max(0, Math.trunc(hit.start)), end: Math.min(text.length, Math.trunc(hit.end)) }))
    // The comparison is false for NaN offsets, so they are dropped as well.
    .filter((range) => range.end > range.start)
    .sort((a, b) => a.start - b.start || b.end - a.end);

  const segments: TextSegment<H>[] = [];
  let cursor = 0;
  for (const range of ranges) {
    const start = Math.max(range.start, cursor);
    if (range.end <= start) continue;
    if (start > cursor) segments.push({ text: text.slice(cursor, start), hit: null });
    segments.push({ text: text.slice(start, range.end), hit: range.hit });
    cursor = range.end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), hit: null });
  return segments;
}
