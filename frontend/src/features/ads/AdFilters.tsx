import { useState } from 'react';
import { useDebouncedCallback } from '@/lib/hooks';
import { useTranslation } from 'react-i18next';
import type { AdStatus, Platform } from '@/api/types';
import { SelectInput } from '@/components/form/SelectInput';
import { TextInput } from '@/components/form/TextInput';
import { ObjectSelect } from '@/components/ObjectSelect';
import { Button } from '@/components/ui/button';
import { useEnumOptions } from '@/i18n/useEnum';
import { AD_STATUSES, PLATFORMS, parseAdStatus, parseDemo, parsePlatform } from './constants';

const SEARCH_DEBOUNCE_MS = 300;

export interface AdFilterValues {
  platform: Platform | null;
  objectId: number | null;
  status: AdStatus | null;
  /** true = demo only, false = without demo, null = all */
  demo: boolean | null;
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
        label={t('filters.demo')}
        placeholder={t('filters.demoAll')}
        data={[
          { value: 'true', label: t('filters.demoOnly') },
          { value: 'false', label: t('filters.demoNone') },
        ]}
        value={values.demo === null ? null : String(values.demo)}
        onChange={(value) => onChange({ demo: parseDemo(value) })}
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
      <Button variant="secondary" className="justify-self-start" disabled={!canReset} onClick={onReset}>
        {t('reset', { ns: 'common' })}
      </Button>
    </div>
  );
}
