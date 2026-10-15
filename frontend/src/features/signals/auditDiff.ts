export interface DiffRow {
  /** dotted path of the changed field, e.g. `sections.note` */
  path: string;
  before: unknown;
  after: unknown;
}

// Deep enough to reach a field inside `sections.<section>.<field>`; arrays and anything deeper are compared as a whole.
const MAX_DEPTH = 3;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function flatten(value: Record<string, unknown> | null, prefix: string, depth: number, out: Map<string, unknown>) {
  if (!value) return;
  for (const [key, item] of Object.entries(value)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (isRecord(item) && depth < MAX_DEPTH) flatten(item, path, depth + 1, out);
    else out.set(path, item);
  }
}

/** Changed fields only, so an update that touched one field is one row instead of two JSON blobs. */
export function auditDiff(before: Record<string, unknown> | null, after: Record<string, unknown> | null): DiffRow[] {
  const oldValues = new Map<string, unknown>();
  const newValues = new Map<string, unknown>();
  flatten(before, '', 1, oldValues);
  flatten(after, '', 1, newValues);

  const paths = new Set([...oldValues.keys(), ...newValues.keys()]);
  const rows: DiffRow[] = [];
  for (const path of paths) {
    const oldValue = oldValues.get(path);
    const newValue = newValues.get(path);
    // A missing key and an explicit null are the same "no value".
    if (JSON.stringify(oldValue ?? null) !== JSON.stringify(newValue ?? null)) rows.push({ path, before: oldValue, after: newValue });
  }
  return rows;
}
