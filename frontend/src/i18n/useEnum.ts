import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import type ruEnums from './locales/ru/enums';

export type EnumGroup = keyof typeof ruEnums;

export interface EnumOption {
  value: string;
  label: string;
}

/** Translates a backend code: `e('doc_type', 'psd')`. Unknown codes are shown as-is. */
export function useEnum() {
  const { t } = useTranslation('enums');
  return useCallback(
    (group: EnumGroup, code: string | null | undefined, options?: Record<string, unknown>): string =>
      code == null || code === '' ? '' : t(`${group}.${code}`, { defaultValue: code, ...options }),
    [t],
  );
}

/** Select/SegmentedControl data for a list of codes. */
export function useEnumOptions() {
  const e = useEnum();
  return useCallback(
    (group: EnumGroup, codes: readonly string[]): EnumOption[] =>
      codes.map((code) => ({ value: code, label: e(group, code) })),
    [e],
  );
}

/** "No permit, booking open", "Idle 45 days": key status plus its detail payload. */
export function useKeyStatusLabel() {
  const e = useEnum();
  return useCallback(
    (status: string | null | undefined, detail?: Record<string, unknown> | null): string => {
      if (!status) return '';
      if (status === 'stalled' && typeof detail?.stalled_days === 'number') {
        return e('key_status', status, { count: detail.stalled_days });
      }
      return e('key_status', status);
    },
    [e],
  );
}
