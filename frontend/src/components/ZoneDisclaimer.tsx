import { IconInfoCircle } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import classes from './ZoneDisclaimer.module.css';

/** D16: must be visible wherever a zone is shown (dashboard, object card, signal card). */
export function ZoneDisclaimer({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <p className={`${classes.root} ${className ?? ''}`} role="note">
      <IconInfoCircle size={15} stroke={1.8} aria-hidden />
      <span>{t('disclaimer.zone')}</span>
    </p>
  );
}
