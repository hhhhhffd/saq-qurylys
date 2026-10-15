import { SegmentedControl } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { setLanguage } from '@/i18n';
import type { Locale } from '@/api/types';

export function LanguageSwitch() {
  const { t, i18n } = useTranslation();
  return (
    <SegmentedControl
      size="xs"
      radius="md"
      aria-label={t('header.language')}
      value={i18n.language === 'kk' ? 'kk' : 'ru'}
      onChange={(value) => setLanguage(value as Locale)}
      data={[
        { value: 'ru', label: 'RU' },
        { value: 'kk', label: 'ҚАЗ' },
      ]}
    />
  );
}
