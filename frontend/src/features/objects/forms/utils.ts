import dayjs from 'dayjs';
import type { TFunction } from 'i18next';

const API_DATE_FORMAT = 'YYYY-MM-DD';
export const DISPLAY_DATE_FORMAT = 'DD.MM.YYYY';

/** Client-side guard for scans, screenshots and photos; the server enforces its own (configurable) limit. */
export const MAX_FILE_MB = 50;
const MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024;

export const SCAN_ACCEPT = 'image/png,image/jpeg,image/webp,application/pdf';
export const PHOTO_ACCEPT = 'image/png,image/jpeg,image/webp';

const DISPLAY_DATE = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/;
const API_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Mantine 9 `DateInput` stores plain `YYYY-MM-DD` strings, which is the API format as well: no time zone shifts. */
export function today(): string {
  return dayjs().format(API_DATE_FORMAT);
}

/** Parses typed `DD.MM.YYYY` (or `YYYY-MM-DD`) into the `YYYY-MM-DD` value `DateInput` stores; rejects impossible dates. */
export function parseDateInput(text: string): string | null {
  const trimmed = text.trim();
  const match = DISPLAY_DATE.exec(trimmed);
  const iso = match ? `${match[3]}-${match[2].padStart(2, '0')}-${match[1].padStart(2, '0')}` : trimmed;
  // dayjs rolls 30 February over to March, so the round trip is what proves the date is real.
  return API_DATE.test(iso) && dayjs(iso).format(API_DATE_FORMAT) === iso ? iso : null;
}

/** Date part of an API timestamp or date, for `DateInput`. */
export function toDateValue(value: string | null | undefined): string | null {
  return value ? value.slice(0, 10) : null;
}

export function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed;
}

/** Fields of `next` that differ from `prev` (deep compare of JSON-like values), for PATCH requests. */
export function changedFields<T extends object>(next: T, prev: T): Partial<T> {
  const changes: Partial<T> = {};
  for (const key of Object.keys(next) as (keyof T)[]) {
    if (JSON.stringify(next[key]) !== JSON.stringify(prev[key])) changes[key] = next[key];
  }
  return changes;
}

export type CoordinateValue = number | string;

/** Rule for one half of a lat/lon pair: range check, and both-or-none (the backend rejects a lone value). */
export function coordinateRule(kind: 'lat' | 'lon', t: TFunction) {
  const limit = kind === 'lat' ? 90 : 180;
  return (value: CoordinateValue, values: Record<'lat' | 'lon', CoordinateValue>) => {
    const other = kind === 'lat' ? values.lon : values.lat;
    if (value === '') return other === '' ? null : t('validation.coordinatesTogether', { ns: 'objectForms' });
    return typeof value === 'number' && Math.abs(value) <= limit
      ? null
      : t(kind === 'lat' ? 'validation.latRange' : 'validation.lonRange', { ns: 'objectForms' });
  };
}

export function fileTooLarge(file: File | null): boolean {
  return file !== null && file.size > MAX_FILE_BYTES;
}
