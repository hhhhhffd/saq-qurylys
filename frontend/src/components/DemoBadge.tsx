import { useTranslation } from 'react-i18next';
import { Chip } from './Chip';

/** D18: demo records (`is_demo`) are fictional and must never be mistaken for facts. */
export function DemoBadge() {
  const { t } = useTranslation();
  return (
    <Chip tone="info" title={t('demo.title')}>
      {t('demo.badge')}
    </Chip>
  );
}
