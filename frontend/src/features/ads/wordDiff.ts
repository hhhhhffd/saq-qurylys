export type DiffKind = 'same' | 'removed' | 'added';

export interface DiffPart {
  text: string;
  kind: DiffKind;
}

// Words and numbers, single punctuation marks, and runs of whitespace. The whitespace is kept to rebuild the text.
const TOKEN = /[\p{L}\p{N}\p{M}_]+|[^\s\p{L}\p{N}\p{M}_]|\s+/gu;
const isSpace = (token: string) => /^\s/.test(token);

// The table of the longest common subsequence has one cell per pair of words; two texts of up to ~2000 words
// each fit. Longer ones are shown as wholly replaced instead of freezing the page.
const MAX_CELLS = 4_000_000;

/** Which words of `a` and of `b` (by position in the word lists) belong to their longest common subsequence. */
function commonWords(a: string[], b: string[]): { keptA: boolean[]; keptB: boolean[] } {
  const keptA: boolean[] = new Array<boolean>(a.length).fill(false);
  const keptB: boolean[] = new Array<boolean>(b.length).fill(false);

  let start = 0;
  while (start < a.length && start < b.length && a[start] === b[start]) {
    keptA[start] = keptB[start] = true;
    start += 1;
  }
  let endA = a.length;
  let endB = b.length;
  while (endA > start && endB > start && a[endA - 1] === b[endB - 1]) {
    endA -= 1;
    endB -= 1;
    keptA[endA] = keptB[endB] = true;
  }

  const rows = endA - start;
  const cols = endB - start;
  if (rows === 0 || cols === 0 || rows * cols > MAX_CELLS) return { keptA, keptB };

  // lcs[i * width + j]: length of the longest common subsequence of a[start + i ..] and b[start + j ..].
  const width = cols + 1;
  const lcs = new Uint16Array((rows + 1) * width);
  for (let i = rows - 1; i >= 0; i -= 1) {
    for (let j = cols - 1; j >= 0; j -= 1) {
      lcs[i * width + j] =
        a[start + i] === b[start + j]
          ? lcs[(i + 1) * width + j + 1] + 1
          : Math.max(lcs[(i + 1) * width + j], lcs[i * width + j + 1]);
    }
  }
  let i = 0;
  let j = 0;
  while (i < rows && j < cols) {
    if (a[start + i] === b[start + j]) {
      keptA[start + i] = keptB[start + j] = true;
      i += 1;
      j += 1;
    } else if (lcs[(i + 1) * width + j] >= lcs[i * width + j + 1]) {
      i += 1;
    } else {
      j += 1;
    }
  }
  return { keptA, keptB };
}

/** Marks every word of one text; whitespace between two changed words belongs to the change. */
function markTokens(tokens: string[], kept: boolean[], changed: DiffKind): DiffPart[] {
  let wordIndex = 0;
  const kinds = tokens.map((token): DiffKind | null => (isSpace(token) ? null : kept[wordIndex++] ? 'same' : changed));
  // Kind of the first word after each token.
  const following: DiffKind[] = new Array<DiffKind>(tokens.length);
  let upcoming: DiffKind = 'same';
  for (let index = tokens.length - 1; index >= 0; index -= 1) {
    following[index] = upcoming;
    upcoming = kinds[index] ?? upcoming;
  }

  const parts: DiffPart[] = [];
  let preceding: DiffKind = 'same';
  tokens.forEach((token, index) => {
    const own = kinds[index];
    const kind = own ?? (preceding === following[index] ? preceding : 'same');
    if (own !== null) preceding = own;
    const last = parts.at(-1);
    if (last && last.kind === kind) last.text += token;
    else parts.push({ text: token, kind });
  });
  return parts;
}

/**
 * Word-level difference of two texts: `before` with the words that are gone marked `removed`, `after` with the
 * words that appeared marked `added`. Concatenating the parts of a side gives back its text exactly.
 */
export function diffWords(before: string, after: string): { before: DiffPart[]; after: DiffPart[] } {
  const tokensBefore = before.match(TOKEN) ?? [];
  const tokensAfter = after.match(TOKEN) ?? [];
  const { keptA, keptB } = commonWords(
    tokensBefore.filter((token) => !isSpace(token)),
    tokensAfter.filter((token) => !isSpace(token)),
  );
  return {
    before: markTokens(tokensBefore, keptA, 'removed'),
    after: markTokens(tokensAfter, keptB, 'added'),
  };
}
