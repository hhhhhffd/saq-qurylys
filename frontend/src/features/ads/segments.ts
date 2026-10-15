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

/** The text read from the photos of a publication follows this marker in `AdRow.text` (SPEC 10.2). */
export const OCR_MARKER = '\n\n[OCR]\n';

export interface TextPart<H extends HitRange> {
  text: string;
  /** hits lying wholly inside the part, with offsets relative to the part */
  hits: H[];
}

/**
 * Splits the text of a publication at the OCR marker (the first one, as the backend does) into the publication's
 * own text and the text recognised on its photos. Hit offsets are indices into the whole text: a hit goes to the
 * part that wholly contains it and is shifted to the part's start; a hit crossing the marker belongs to neither,
 * so no hit is ever cut.
 */
export function splitOcr<H extends HitRange>(
  text: string,
  hits: readonly H[],
): { own: TextPart<H>; ocr: TextPart<H> | null } {
  const markerAt = text.indexOf(OCR_MARKER);
  if (markerAt === -1) return { own: { text, hits: [...hits] }, ocr: null };
  const ocrStart = markerAt + OCR_MARKER.length;
  return {
    own: { text: text.slice(0, markerAt), hits: hits.filter((hit) => hit.end <= markerAt) },
    ocr: {
      text: text.slice(ocrStart),
      hits: hits
        .filter((hit) => hit.start >= ocrStart)
        .map((hit) => ({ ...hit, start: hit.start - ocrStart, end: hit.end - ocrStart })),
    },
  };
}
