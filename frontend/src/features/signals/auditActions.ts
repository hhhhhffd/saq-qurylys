// Action codes are defined by the backend (e.g. `signal_card.confirm_and_send`), so they are matched loosely
// on the last dotted segment; unknown codes are shown as they are.
const PATTERNS: [RegExp, string][] = [
  [/confirm|send|sent/, 'sent'],
  [/return/, 'returned'],
  [/respon/, 'responded'],
  [/clos/, 'closed'],
  [/creat/, 'created'],
  [/updat|edit|patch|change/, 'updated'],
];

export function auditActionKey(action: string): string | null {
  const segment = action.toLowerCase().split(/[./:]/).pop() ?? '';
  return PATTERNS.find(([pattern]) => pattern.test(segment))?.[1] ?? null;
}
