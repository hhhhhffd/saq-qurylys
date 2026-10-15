import { useTranslation } from 'react-i18next';
import type { SignalStatus } from '@/api/types';
import { Chip } from '@/components/Chip';
import { useFormat } from '@/i18n/useFormat';
import { cn } from '@/lib/utils';

interface Props {
  dueDate: string | null;
  status: SignalStatus;
  isOverdue: boolean;
}

/** Review deadline: the date, an overdue marker, and the days left while the card waits for the body. */
export function DueInfo({ dueDate, status, isOverdue }: Props) {
  const { t } = useTranslation('signals');
  const { date, daysUntil } = useFormat();
  if (!dueDate) return <span className="text-text-3">—</span>;

  const daysLeft = status === 'sent' && !isOverdue ? daysUntil(dueDate) : null;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
      <span className={cn('tabular-nums', isOverdue && 'text-zone-red-ink')}>{date(dueDate)}</span>
      {isOverdue && <Chip tone="red">{t('due.overdue')}</Chip>}
      {daysLeft !== null && (
        <span className="text-xs text-text-3">{daysLeft > 0 ? t('due.daysLeft', { count: daysLeft }) : t('due.today')}</span>
      )}
    </span>
  );
}
