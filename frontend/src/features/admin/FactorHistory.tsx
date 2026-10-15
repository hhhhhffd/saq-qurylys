import { useTranslation } from 'react-i18next';
import { useRiskFactorHistory } from '@/api/hooks/reference';
import type { RiskFactorChange } from '@/api/types';
import { dataColumns } from '@/components/dataColumns';
import { DataTable } from '@/components/DataTable';
import { QueryBoundary } from '@/components/QueryState';
import { useFormat } from '@/i18n/useFormat';
import { SectionHeader } from './SectionHeader';
import { useFactorLabels } from './useFactorLabels';
import { usePagedRows } from './usePagedRows';

const PAGE_SIZE = 10;
const col = dataColumns<RiskFactorChange>();

/** `40 → 45`, or a dash when the value did not change in this entry. */
function transition(from: string | null, to: string | null): string {
  if (from === to) return '—';
  return `${from ?? '—'} → ${to ?? '—'}`;
}

function HistoryTable({ changes }: { changes: RiskFactorChange[] }) {
  const { t } = useTranslation('admin');
  const { t: tc } = useTranslation('common');
  const format = useFormat();
  const labels = useFactorLabels();
  const newestFirst = [...changes].sort((a, b) => Date.parse(b.changed_at) - Date.parse(a.changed_at));
  const { pageRows, pageIndex, setPageIndex } = usePagedRows(newestFirst, PAGE_SIZE);

  const yesNo = (value: boolean | null) => (value === null ? null : value ? tc('yes') : tc('no'));

  const columns = [
    col.display({
      id: 'at',
      header: t('factors.history.columns.at'),
      cell: ({ row }) => <span className="tabular-nums">{format.dateTime(row.original.changed_at)}</span>,
    }),
    col.display({
      id: 'factor',
      header: t('factors.history.columns.factor'),
      cell: ({ row }) => labels.name(row.original.code),
    }),
    col.display({
      id: 'weight',
      header: t('factors.history.columns.weight'),
      cell: ({ row }) => (
        <span className="tabular-nums">
          {transition(row.original.old_weight?.toString() ?? null, row.original.new_weight?.toString() ?? null)}
        </span>
      ),
    }),
    col.display({
      id: 'active',
      header: t('factors.history.columns.active'),
      cell: ({ row }) => transition(yesNo(row.original.old_active), yesNo(row.original.new_active)),
    }),
    col.display({
      id: 'by',
      header: t('factors.history.columns.by'),
      cell: ({ row }) => {
        const { changed_by_name: name, changed_by: id } = row.original;
        return name ?? (id === null ? '—' : `#${id}`);
      },
    }),
  ];

  return (
    <DataTable
      columns={columns}
      data={pageRows}
      total={newestFirst.length}
      pageIndex={pageIndex}
      pageSize={PAGE_SIZE}
      onPageChange={setPageIndex}
      emptyText={t('factors.history.empty')}
    />
  );
}

export function FactorHistory() {
  const { t } = useTranslation('admin');
  const query = useRiskFactorHistory();

  return (
    <section>
      <SectionHeader title={t('factors.history.title')} />
      <QueryBoundary query={query}>{(changes) => <HistoryTable changes={changes} />}</QueryBoundary>
    </section>
  );
}
