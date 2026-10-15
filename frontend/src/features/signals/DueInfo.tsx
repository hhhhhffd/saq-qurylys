import { useTranslation } from 'react-i18next';
import type { SignalStatus } from '@/api/types';
import { Chip } from '@/components/Chip';
import { useFormat } from '@/i18n/useFormat';
import classes from './DueInfo.module.css';

interface Props {
  dueDate: string | null;
  status: SignalStatus;
  isOverdue: boolean;
}

/** Review deadline: the date, an overdue marker, and the days left while the card waits for the body. */
export function DueInfo({ dueDate, status, isOverdue }: Props) {
  const { t } = useTranslation('signals');
  const { date, daysUntil } = useFormat();
  if (!dueDate) return <span className="faint">—</span>;

  const daysLeft = status === 'sent' && !isOverdue ? daysUntil(dueDate) : null;
  return (
    <span className={classes.root}>
      <span className="tnum">{date(dueDate)}</span>
      {isOverdue && <Chip tone="red">{t('due.overdue')}</Chip>}
      {daysLeft !== null && (
        <span className="faint">{daysLeft > 0 ? t('due.daysLeft', { count: daysLeft }) : t('due.today')}</span>
      )}
    </span>
  );
}
