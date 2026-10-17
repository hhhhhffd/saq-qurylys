import { useState } from 'react';
import { IconUserCheck } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useObjectAssignments } from '@/api/hooks/assignments';
import type { ObjectDetail } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Panel } from '@/components/Panel';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { AssignFormModal } from '@/features/assignments/AssignFormModal';
import { AssignmentActions } from '@/features/assignments/AssignmentActions';
import { AssignmentState } from '@/features/assignments/AssignmentState';
import { useFormat } from '@/i18n/useFormat';

export function AssignmentsSection({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('assignments');
  const { date } = useFormat();
  const { canEditRegistry } = useAuth();
  const [adding, setAdding] = useState(false);
  const query = useObjectAssignments(object.id);

  // Open ones first, then the history.
  const items = [...(query.data ?? [])].sort(
    (a, b) => Number(b.status === 'open') - Number(a.status === 'open') || a.due_date.localeCompare(b.due_date),
  );

  return (
    <Panel
      title={t('section.title')}
      id="assignments"
      flush
      actions={
        canEditRegistry && (
          <Button className="min-h-11" onClick={() => setAdding(true)}>
            <IconUserCheck />
            {t('section.add')}
          </Button>
        )
      }
    >
      {query.isPending ? (
        <LoadingBlock />
      ) : query.isError ? (
        <ErrorBlock error={query.error} onRetry={() => void query.refetch()} />
      ) : items.length === 0 ? (
        <p className="px-4 pb-4 text-text-3">{t('section.empty')}</p>
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item.id} className="border-t border-border px-4 py-3 first:border-t-0">
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
                <strong className="[overflow-wrap:anywhere]">{item.task}</strong>
                <span className="ml-auto">
                  <AssignmentState assignment={item} />
                </span>
              </div>
              <p className="mt-1 text-sm text-text-2">
                {t('section.assignee')}: {item.assignee_name} · {t('section.due')}:{' '}
                <span className="tabular-nums">{date(item.due_date)}</span> · {t('section.author')}: {item.author_name}
              </p>
              {item.result && (
                <p className="mt-1 text-sm [overflow-wrap:anywhere]">
                  <span className="text-text-3">{t('section.result')}:</span> {item.result}
                </p>
              )}
              <AssignmentActions assignment={item} />
            </li>
          ))}
        </ul>
      )}
      {canEditRegistry && <AssignFormModal opened={adding} onClose={() => setAdding(false)} objectId={object.id} />}
    </Panel>
  );
}
