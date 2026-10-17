import { useTranslation } from 'react-i18next';
import type { Assignment } from '@/api/types';
import { Chip } from '@/components/Chip';

/** The state in words; an overdue one says by how many days, so colour is never the only signal. */
export function AssignmentState({ assignment }: { assignment: Assignment }) {
  const { t } = useTranslation('assignments');
  if (assignment.is_overdue) {
    return <Chip tone="red">{t('overdue', { count: assignment.days_overdue })}</Chip>;
  }
  const tone = assignment.status === 'done' ? 'green' : assignment.status === 'cancelled' ? 'neutral' : 'info';
  return <Chip tone={tone}>{t(`status.${assignment.status}`)}</Chip>;
}
