import dayjs from 'dayjs';
import type { TFunction } from 'i18next';
import type { z } from 'zod';

/** Client-side guard for scans, screenshots and photos; the server enforces its own (configurable) limit. */
export const MAX_FILE_MB = 25;
const MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024;

export const SCAN_ACCEPT = 'image/png,image/jpeg,image/webp,application/pdf';
export const PHOTO_ACCEPT = 'image/png,image/jpeg,image/webp';

/** Today as the plain `YYYY-MM-DD` string the date fields store and the API takes: no time zone shifts. */
export function today(): string {
  return dayjs().format('YYYY-MM-DD');
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

/** A number, `''` when empty, or a string while an unfinished number is typed. */
export type CoordinateValue = number | string;

/**
 * Adds the errors of a lat/lon pair to a schema (`superRefine`): range check, and both-or-none
 * (the backend rejects a lone value).
 */
export function checkCoordinates(values: Record<'lat' | 'lon', CoordinateValue>, ctx: z.RefinementCtx, t: TFunction) {
  for (const kind of ['lat', 'lon'] as const) {
    const limit = kind === 'lat' ? 90 : 180;
    const value = values[kind];
    const other = values[kind === 'lat' ? 'lon' : 'lat'];
    let message: string | null = null;
    if (value === '') {
      if (other !== '') message = t('validation.coordinatesTogether', { ns: 'objectForms' });
    } else if (typeof value !== 'number' || Math.abs(value) > limit) {
      message = t(kind === 'lat' ? 'validation.latRange' : 'validation.lonRange', { ns: 'objectForms' });
    }
    if (message) ctx.addIssue({ code: 'custom', message, path: [kind] });
  }
}

export function fileTooLarge(file: File | null): boolean {
  return file !== null && file.size > MAX_FILE_BYTES;
}
