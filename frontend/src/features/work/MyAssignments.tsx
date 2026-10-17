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
    <section className="border-y border-border py-3" aria-labelledby="my-assignments-title">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 id="my-assignments-title" className="text-sm font-semibold">
          {t('mine.title')}
        </h2>
        <Link to="/control" className="inline-flex min-h-11 items-center text-sm">
          {t('mine.all')}
        </Link>
      </div>
      {query.isPending ? (
        <LoadingBlock />
      ) : query.isError ? (
        <ErrorBlock error={query.error} onRetry={() => void query.refetch()} />
      ) : query.data.items.length === 0 ? (
        <p className="m-0 text-sm text-text-3">{t('mine.empty')}</p>
      ) : (
        <ul className="m-0 list-none space-y-3 p-0">
          {query.data.items.map((item) => (
            <li key={item.id}>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <Link to={`/objects/${item.object.id}`} className="font-semibold">
                  {item.object.name}
                </Link>
                <AssignmentState assignment={item} />
                <span className="text-sm text-text-2">
                  {t('section.due')}: <span className="tabular-nums">{date(item.due_date)}</span>
                </span>
              </div>
              <p className="m-0 mt-1 text-sm [overflow-wrap:anywhere]">{item.task}</p>
              <AssignmentActions assignment={item} />
            </li>
          ))}
        </ul>
      )}
      {query.data && query.data.total > SHOWN && (
        <p className="m-0 mt-2 text-xs text-text-3">{t('mine.more', { shown: SHOWN, total: query.data.total })}</p>
      )}
    </section>
  );
}
