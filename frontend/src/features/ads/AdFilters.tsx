import { useState } from 'react';
import { Button, Select, TextInput } from '@mantine/core';
import { useDebouncedCallback } from '@mantine/hooks';
import { IconSearch } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import type { AdStatus, Platform } from '@/api/types';
import { ObjectSelect } from '@/components/ObjectSelect';
import { useEnumOptions } from '@/i18n/useEnum';
import { AD_STATUSES, PLATFORMS, parseAdStatus, parseDemo, parsePlatform } from './constants';
import classes from './AdFilters.module.css';

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
    <div className={`panel ${classes.filters}`} role="search">
      <Select
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
      <Select
        label={t('filters.status')}
        placeholder={t('filters.statusAll')}
        data={options('ad_status', AD_STATUSES)}
        value={values.status}
        onChange={(value) => onChange({ status: parseAdStatus(value) })}
        clearable
      />
      <Select
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
        leftSection={<IconSearch size={16} stroke={1.8} />}
        value={text}
        onChange={(event) => {
          setText(event.currentTarget.value);
          commitSearch(event.currentTarget.value);
        }}
      />
      <Button variant="default" className={classes.reset} disabled={!canReset} onClick={onReset}>
        {t('reset', { ns: 'common' })}
      </Button>
    </div>
  );
}
