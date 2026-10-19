import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { useAssignments } from '@/api/hooks/assignments';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { AssignmentActions } from '@/features/assignments/AssignmentActions';
import { AssignmentState } from '@/features/assignments/AssignmentState';
import { useFormat } from '@/i18n/useFormat';

const SHOWN = 5;

/** Open assignments given to the current user, overdue first. */
export function MyAssignments() {
  const { t } = useTranslation('assignments');
  const { date } = useFormat();
  const query = useAssignments({ mine: true, status: 'open', limit: SHOWN });

  return (
    <section className="space-y-2" aria-labelledby="my-assignments-title">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="my-assignments-title" className="text-lg font-semibold">
          {t('mine.title')}
        </h2>
        <Link to="/control" className="inline-flex min-h-11 items-center text-sm">
          {t('mine.all')}
        </Link>
      </div>
      <div className="rounded border border-border bg-surface px-3">
        {query.isPending ? (
          <LoadingBlock />
        ) : query.isError ? (
          <ErrorBlock error={query.error} onRetry={() => void query.refetch()} />
        ) : query.data.items.length === 0 ? (
          <p className="my-3 text-sm text-text-3">{t('mine.empty')}</p>
        ) : (
          <ul className="m-0 list-none divide-y divide-border p-0">
            {query.data.items.map((item) => (
              <li key={item.id} className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 py-2">
                <div className="min-w-0 flex-1 basis-60">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <Link to={`/objects/${item.object.id}`} className="text-sm font-semibold">
                      {item.object.name}
                    </Link>
                    <AssignmentState assignment={item} />
                    <span className="text-xs text-text-3">
                      {t('section.due')}: <span className="tabular-nums">{date(item.due_date)}</span>
                    </span>
                  </div>
                  <p className="m-0 mt-0.5 text-sm text-text-2 [overflow-wrap:anywhere]">{item.task}</p>
                </div>
                <AssignmentActions assignment={item} compact />
              </li>
            ))}
          </ul>
        )}
      </div>
      {query.data && query.data.total > SHOWN && (
        <p className="m-0 text-xs text-text-3">{t('mine.more', { shown: SHOWN, total: query.data.total })}</p>
      )}
    </section>
  );
}
