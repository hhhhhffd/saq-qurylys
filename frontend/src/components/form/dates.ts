import { format, isValid, parse } from 'date-fns';
import { kk } from 'date-fns/locale/kk';
import { ru } from 'date-fns/locale/ru';

/** date-fns locale of the UI language; the week starts on Monday in both. */
export function calendarLocale(language: string) {
  return language === 'kk' ? kk : ru;
}

/** What the API and the form values use: `2026-10-13`. */
export const API_DATE = 'yyyy-MM-dd';
/** What a date-time value is stored as (local time, no zone), like the Mantine picker did: `2026-10-13 18:30:00`. */
export const API_DATE_TIME = 'yyyy-MM-dd HH:mm:ss';
/** What the user types and reads. */
export const DISPLAY_DATE = 'dd.MM.yyyy';
export const DISPLAY_DATE_TIME = 'dd.MM.yyyy HH:mm';

/** `YYYY-MM-DD` (or a longer ISO string) to a local date; null for empty or impossible values. */
export function parseApiDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = parse(value.slice(0, 10), API_DATE, new Date());
  return isValid(date) ? date : null;
}

/** `YYYY-MM-DD HH:mm[:ss]` (or ISO with `T`) to a local date-time. */
export function parseApiDateTime(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = parse(value.replace('T', ' ').slice(0, 16), 'yyyy-MM-dd HH:mm', new Date());
  return isValid(date) ? date : null;
}

const TYPED_DATE = /^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/;
const TYPED_DATE_TIME = /^(\d{1,2})[./-](\d{1,2})[./-](\d{4})[ T]+(\d{1,2}):(\d{2})$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
const ISO_DATE_TIME = /^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}$/;

/** Builds a date only if the parts round-trip, so 30.02.2026 is rejected instead of rolling over to March. */
function fromParts(year: number, month: number, day: number, hour = 0, minute = 0): Date | null {
  const date = new Date(year, month - 1, day, hour, minute);
  const same = date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day && date.getHours() === hour && date.getMinutes() === minute;
  return same ? date : null;
}

/** Typed `DD.MM.YYYY` (or `YYYY-MM-DD`); null while the text is not a real date. */
export function parseTypedDate(text: string): Date | null {
  const trimmed = text.trim();
  const typed = TYPED_DATE.exec(trimmed);
  if (typed) return fromParts(Number(typed[3]), Number(typed[2]), Number(typed[1]));
  return ISO_DATE.test(trimmed) ? parseApiDate(trimmed) : null;
}

/** Typed `DD.MM.YYYY HH:mm` (or `YYYY-MM-DD HH:mm`); null while the text is not a real date-time. */
export function parseTypedDateTime(text: string): Date | null {
  const trimmed = text.trim();
  const typed = TYPED_DATE_TIME.exec(trimmed);
  if (typed) {
    const [, day, month, year, hour, minute] = typed;
    return fromParts(Number(year), Number(month), Number(day), Number(hour), Number(minute));
  }
  return ISO_DATE_TIME.test(trimmed) ? parseApiDateTime(trimmed) : null;
}

export const formatApiDate = (date: Date) => format(date, API_DATE);
export const formatApiDateTime = (date: Date) => format(date, API_DATE_TIME);
export const formatDisplayDate = (date: Date | null) => (date ? format(date, DISPLAY_DATE) : '');
export const formatDisplayDateTime = (date: Date | null) => (date ? format(date, DISPLAY_DATE_TIME) : '');
