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

const SCORE_RANGE = /^score_(\d+)_(\d+)$/;
const SCORE_WITHOUT_R1_R2 = /^score_(\d+)_without_r1_r2$/;

/** `zone_reasons` codes embed the zone thresholds (`score_25_59`), so they are turned into text by their numbers. */
export function useZoneReasonLabel() {
  const e = useEnum();
  return useCallback(
    (code: string): string => {
      const range = SCORE_RANGE.exec(code);
      if (range) return e('zone_reason', 'score_range', { from: range[1], to: range[2] });
      const without = SCORE_WITHOUT_R1_R2.exec(code);
      if (without) return e('zone_reason', 'score_without_r1_r2', { from: without[1] });
      return e('zone_reason', code);
    },
    [e],
  );
}
