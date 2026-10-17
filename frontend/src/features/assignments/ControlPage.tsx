import { useNavigate, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useAssignments } from '@/api/hooks/assignments';
import type { Assignment, AssignmentListParams } from '@/api/types';
import { dataColumns } from '@/components/dataColumns';
import { DataTable } from '@/components/DataTable';
import { PageHeader } from '@/components/PageHeader';
import { ErrorBlock } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { useFormat } from '@/i18n/useFormat';
import { AssignmentState } from './AssignmentState';

const PAGE_SIZE = 25;
const FILTERS = ['all', 'overdue', 'open', 'done'] as const;
type Filter = (typeof FILTERS)[number];

const FILTER_PARAMS: Record<Filter, AssignmentListParams> = {
  all: {},
  overdue: { overdue: true },
  open: { status: 'open' },
  done: { status: 'done' },
};

const col = dataColumns<Assignment>();

export function ControlPage() {
  const { t } = useTranslation('assignments');
  const { date } = useFormat();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const requested = params.get('filter');
  const filter: Filter = FILTERS.find((item) => item === requested) ?? 'all';
  const pageIndex = Math.max(0, Number(params.get('page') ?? 1) - 1) || 0;

  const query = useAssignments({ ...FILTER_PARAMS[filter], limit: PAGE_SIZE, offset: pageIndex * PAGE_SIZE });

  const setQuery = (patch: { filter?: Filter; page?: number }) => {
    const next = new URLSearchParams(params);
    if (patch.filter !== undefined) {
      if (patch.filter === 'all') next.delete('filter');
      else next.set('filter', patch.filter);
      next.delete('page');
    }
    if (patch.page !== undefined) {
      if (patch.page === 0) next.delete('page');
      else next.set('page', String(patch.page + 1));
    }
    setParams(next);
  };

  const columns = col.columns([
    col.accessor((row) => row.object.name, {
      id: 'object',
      header: t('control.columns.object'),
      cell: (info) => <span className="font-medium">{info.getValue()}</span>,
    }),
    col.accessor('task', {
      header: t('control.columns.task'),
      cell: (info) => <span className="[overflow-wrap:anywhere]">{info.getValue()}</span>,
    }),
    col.accessor('assignee_name', { header: t('control.columns.assignee') }),
    col.accessor('author_name', { header: t('control.columns.author') }),
    col.accessor('due_date', {
      header: t('control.columns.due'),
      cell: (info) => <span className="whitespace-nowrap tabular-nums">{date(info.getValue())}</span>,
    }),
    col.display({
      id: 'state',
      header: t('control.columns.state'),
      cell: (info) => <AssignmentState assignment={info.row.original} />,
    }),
  ]);

  return (
    <>
      <PageHeader title={t('control.title')} subtitle={t('control.subtitle')} />
      <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label={t('control.title')}>
        {FILTERS.map((item) => (
          <Button
            key={item}
            className="min-h-11"
            variant={item === filter ? 'default' : 'secondary'}
            aria-pressed={item === filter}
            onClick={() => setQuery({ filter: item })}
          >
            {t(`control.filters.${item}`)}
          </Button>
        ))}
      </div>
      {query.isError && !query.data ? (
        <ErrorBlock error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <DataTable
          columns={columns}
          data={query.data?.items ?? []}
          total={query.data?.total ?? 0}
          pageIndex={pageIndex}
          pageSize={PAGE_SIZE}
          onPageChange={(next) => setQuery({ page: next })}
          onRowClick={(row) => void navigate(`/objects/${row.object.id}`)}
          getRowId={(row) => String(row.id)}
          loading={query.isPending}
          fetching={query.isFetching && !query.isPending}
          emptyText={t('control.empty')}
        />
      )}
    </>
  );
}
