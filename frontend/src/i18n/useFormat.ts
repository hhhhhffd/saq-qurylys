import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth/useAuth';
import { useTerritories } from '@/api/hooks/reference';
import { flattenTerritories } from '@/lib/geo';

const DEFAULT_TIME_ZONE = 'Asia/Almaty';
const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const INTL_LOCALE = { ru: 'ru-RU', kk: 'kk-KZ' } as const;

/** Time zone of the user's territory (SPEC §2: display in the territory's zone). */
export function useTimeZone(): string {
  const { user } = useAuth();
  const { data } = useTerritories();
  const territoryId = user?.territory_id ?? null;
  return useMemo(() => {
    const territory = data && territoryId !== null ? flattenTerritories(data).find((t) => t.id === territoryId) : null;
    return territory?.timezone ?? DEFAULT_TIME_ZONE;
  }, [data, territoryId]);
}

type Input = string | number | Date | null | undefined;

/** Locale- and timezone-aware formatters. Plain dates (YYYY-MM-DD) are never shifted by a zone. */
export function useFormat() {
  const { i18n } = useTranslation();
  const timeZone = useTimeZone();
  const locale = INTL_LOCALE[i18n.language === 'kk' ? 'kk' : 'ru'];

  return useMemo(() => {
    const dateFmt = new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'UTC' });
    const zonedDateFmt = new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit', year: 'numeric', timeZone });
    const dateTimeFmt = new Intl.DateTimeFormat(locale, {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      timeZone,
    });
    const numberFmt = new Intl.NumberFormat(locale);

    const toDate = (value: Input): Date | null => {
      if (value == null || value === '') return null;
      const date = value instanceof Date ? value : new Date(value);
      return Number.isNaN(date.getTime()) ? null : date;
    };

    return {
      locale,
      timeZone,
      /** `13.10.2026`; plain dates are shown as-is, timestamps in the territory zone */
      date: (value: Input): string => {
        const date = toDate(value);
        if (!date) return '—';
        return typeof value === 'string' && DATE_ONLY.test(value) ? dateFmt.format(date) : zonedDateFmt.format(date);
      },
      /** `13.10.2026, 14:05` in the territory zone */
      dateTime: (value: Input): string => {
        const date = toDate(value);
        return date ? dateTimeFmt.format(date) : '—';
      },
      number: (value: number | null | undefined): string => (value == null ? '—' : numberFmt.format(value)),
      /** whole days between a date and now, positive = in the future */
      daysUntil: (value: Input): number | null => {
        const date = toDate(value);
        return date ? Math.ceil((date.getTime() - Date.now()) / 86_400_000) : null;
      },
    };
  }, [locale, timeZone]);
}
