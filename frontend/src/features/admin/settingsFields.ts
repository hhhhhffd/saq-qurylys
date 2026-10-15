import type { AppSettings, SignalRecipient } from '@/api/types';

interface NumericField {
  min: number;
  max: number;
  /** omitted for integers */
  step?: number;
  decimals?: number;
}

/** Ranges mirror the backend validation of `PUT /settings`. */
export const NUMERIC_FIELDS = {
  review_days: { min: 1, max: 60 },
  ad_window_days: { min: 1, max: 365 },
  readiness_gap_pp: { min: 1, max: 100 },
  significant_delay_days: { min: 1, max: 3650 },
  zone_yellow_min: { min: 1, max: 100 },
  zone_red_min: { min: 1, max: 100 },
  stalled_days: { min: 1, max: 3650 },
  recheck_after_days: { min: 1, max: 365 },
  link_confidence_threshold: { min: 0, max: 1, step: 0.05, decimals: 2 },
  green_interval_days: { min: 1, max: 365 },
  yellow_interval_days: { min: 1, max: 365 },
} satisfies Record<string, NumericField>;

export type NumericSettingKey = keyof typeof NUMERIC_FIELDS;

export const NUMERIC_KEYS = Object.keys(NUMERIC_FIELDS) as NumericSettingKey[];

export function numericField(key: NumericSettingKey): NumericField {
  return NUMERIC_FIELDS[key];
}

export const NUMERIC_GROUPS: { id: 'review' | 'ads' | 'risk' | 'zones' | 'schedule'; keys: NumericSettingKey[] }[] = [
  { id: 'review', keys: ['review_days'] },
  { id: 'ads', keys: ['ad_window_days', 'link_confidence_threshold', 'recheck_after_days'] },
  { id: 'risk', keys: ['readiness_gap_pp', 'significant_delay_days', 'stalled_days'] },
  { id: 'zones', keys: ['zone_yellow_min', 'zone_red_min'] },
  { id: 'schedule', keys: ['green_interval_days', 'yellow_interval_days'] },
];

export const RECIPIENTS: SignalRecipient[] = ['mio', 'gask', 'law_enforcement'];

/** Form state: NumberInput reports a string while the field is empty or half-typed. */
export type SettingsFormValues = { [K in NumericSettingKey]: number | string } & Pick<AppSettings, 'recipient_emails'>;

export const EMAIL_PATTERN = /^\S+@\S+$/;

export function toFormValues(settings: AppSettings): SettingsFormValues {
  // `complaints_threshold` is stored but no longer used by the risk model, so it is not editable.
  const { recipient_emails: emails, complaints_threshold: _unused, ...numbers } = settings;
  // The backend stores only the bodies that were ever saved, so a missing body means "no addresses".
  return {
    ...numbers,
    recipient_emails: { mio: emails.mio ?? [], gask: emails.gask ?? [], law_enforcement: emails.law_enforcement ?? [] },
  };
}
