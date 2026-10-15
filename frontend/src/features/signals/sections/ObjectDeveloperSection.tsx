import { useTranslation } from 'react-i18next';
import type { SignalSections } from '@/api/types';
import { KeyValue } from '@/components/KeyValue';
import { Panel } from '@/components/Panel';

export function ObjectDeveloperSection({ data }: { data: SignalSections['object_developer'] }) {
  const { t } = useTranslation('signals');
  return (
    <Panel title={t('sections.object_developer')}>
      <KeyValue
        columns={3}
        items={[
          { label: t('objectDeveloper.code'), value: data.object_code },
          { label: t('objectDeveloper.name'), value: data.object_name },
          { label: t('objectDeveloper.cadastral'), value: data.cadastral_number },
          { label: t('objectDeveloper.address'), value: data.address, wide: true },
          { label: t('objectDeveloper.landPurpose'), value: data.land_purpose, wide: true },
          { label: t('objectDeveloper.developer'), value: data.developer_name },
          { label: t('objectDeveloper.bin'), value: data.bin },
          { label: t('objectDeveloper.director'), value: data.director },
          { label: t('objectDeveloper.founders'), value: data.founders.join(', '), wide: true },
        ]}
      />
    </Panel>
  );
}
