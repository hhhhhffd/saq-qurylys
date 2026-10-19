import { useState } from 'react';
import { useDebouncedCallback } from '@/lib/hooks';
import { useTranslation } from 'react-i18next';
import type { AdReviewState, AdStatus, Platform } from '@/api/types';
import { SelectInput } from '@/components/form/SelectInput';
import { TextInput } from '@/components/form/TextInput';
import { ObjectSelect } from '@/components/ObjectSelect';
import { Button } from '@/components/ui/button';
import { useEnumOptions } from '@/i18n/useEnum';
import { AD_REVIEW_STATES, AD_STATUSES, PLATFORMS, parseAdStatus, parseReviewState, parsePlatform } from './constants';

const SEARCH_DEBOUNCE_MS = 300;

export interface AdFilterValues {
  platform: Platform | null;
  objectId: number | null;
  status: AdStatus | null;
  reviewState: AdReviewState | null;
  q: string;
}

interface Props {
  values: AdFilterValues;
  onChange: (patch: Partial<AdFilterValues>) => void;
  onReset: () => void;
  canReset: boolean;
}

export function AdFilters({ values, onChange, onReset, canReset }: Props) {
  const { t } = useTranslation('ads');
  const options = useEnumOptions();
  // The input keeps its own text while typing; the URL value is adopted when it changes elsewhere (reset, history).
  const [text, setText] = useState(values.q);
  const [syncedQ, setSyncedQ] = useState(values.q);
  if (values.q !== syncedQ) {
    setSyncedQ(values.q);
    setText(values.q);
  }
  const commitSearch = useDebouncedCallback((value: string) => onChange({ q: value }), SEARCH_DEBOUNCE_MS);

  return (
    <div
      className="mb-4 grid grid-cols-1 items-end gap-3 rounded border border-border bg-surface px-4 py-3 sm:grid-cols-2 xl:grid-cols-[repeat(5,minmax(0,1fr))_auto]"
      role="search"
    >
      <div className="grid grid-cols-1 gap-3 sm:col-span-2 sm:grid-cols-2 xl:col-span-5 xl:grid-cols-5">
        <SelectInput
          label={t('filters.platform')}
          placeholder={t('filters.platformAll')}
          data={options('platform', PLATFORMS)}
          value={values.platform}
          onChange={(value) => onChange({ platform: parsePlatform(value) })}
          clearable
        />
        <ObjectSelect
          label={t('filters.object')}
          placeholder={t('filters.objectAll')}
          value={values.objectId}
          onChange={(objectId) => onChange({ objectId })}
        />
        <SelectInput
          label={t('filters.status')}
          placeholder={t('filters.statusAll')}
          data={options('ad_status', AD_STATUSES)}
          value={values.status}
          onChange={(value) => onChange({ status: parseAdStatus(value) })}
          clearable
        />
        <SelectInput
          label={t('filters.reviewState')}
          placeholder={t('filters.reviewStateAll')}
          data={options('ad_review_state', AD_REVIEW_STATES)}
          value={values.reviewState}
          onChange={(value) => onChange({ reviewState: parseReviewState(value) })}
          clearable
        />
        <TextInput
          label={t('filters.search')}
          placeholder={t('filters.searchPlaceholder')}
          value={text}
          onChange={(event) => {
            setText(event.currentTarget.value);
            commitSearch(event.currentTarget.value);
          }}
        />
      </div>
      <Button variant="secondary" className="justify-self-start" disabled={!canReset} onClick={onReset}>
        {t('reset', { ns: 'common' })}
      </Button>
    </div>
  );
}
