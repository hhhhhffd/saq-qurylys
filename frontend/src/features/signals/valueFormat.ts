const MAX_TEXT = 160;

export interface BoolLabels {
  yes: string;
  no: string;
}

export function humanizeKey(key: string): string {
  const text = key.replace(/[_.]+/g, ' ').trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function isPrimitive(value: unknown): value is string | number | boolean | null | undefined {
  return value === null || value === undefined || typeof value !== 'object';
}

function truncate(text: string): string {
  return text.length > MAX_TEXT ? `${text.slice(0, MAX_TEXT)}…` : text;
}

/** Short one-line text for backend-defined values; nested structures are collapsed, never dumped as JSON. */
export function formatPlain(value: unknown, labels: BoolLabels): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return value ? labels.yes : labels.no;
  if (typeof value === 'string' || typeof value === 'number') return truncate(String(value));
  if (Array.isArray(value)) {
    return value.every(isPrimitive) ? truncate(value.map((item) => formatPlain(item, labels)).join(', ')) : '…';
  }
  return '…';
}
