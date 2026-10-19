import { useState } from 'react';
import { IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { useVisionSessions } from '@/api/hooks/vision';
import type { VisionSessionListItem } from '@/api/types';
import { dataColumns } from '@/components/dataColumns';
import { DataTable } from '@/components/DataTable';
import { SelectInput } from '@/components/form/SelectInput';
import { ErrorBlock } from '@/components/QueryState';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/ui/button';
import { useEnum, useEnumOptions } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { parseId, patchParams } from '@/features/objects/list/filters';
import { SESSION_STATUSES, SOURCES, isSessionStatus, isSource } from './constants';
import { NewSessionDialog } from './NewSessionDialog';
import { SessionStatusChips } from './SessionStatusChips';

const PAGE_SIZE = 25;
const col = dataColumns<VisionSessionListItem>();

export function VisionPage() {
  const { t } = useTranslation('vision');
  const e = useEnum();
  const options = useEnumOptions();
  const f = useFormat();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [creating, setCreating] = useState(false);

  const sourceParam = params.get('source');
  const statusParam = params.get('status');
  const source = isSource(sourceParam) ? sourceParam : null;
  const status = isSessionStatus(statusParam) ? statusParam : null;
  const pageIndex = (parseId(params.get('page')) ?? 1) - 1;
  const setFilters = (patch: Record<string, string | null>) => setParams((prev) => patchParams(prev, { ...patch, page: null }));

  const query = useVisionSessions({
    source: source ?? undefined,
    status: status ?? undefined,
    limit: PAGE_SIZE,
    offset: pageIndex * PAGE_SIZE,
  });

  const columns = col.columns([
    col.display({
      id: 'date',
      header: t('columns.date'),
      cell: (info) => {
        const session = info.row.original;
        return (
          <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
            <Link to={`/vision/${session.id}`} className="whitespace-nowrap tabular-nums" onClick={(event) => event.stopPropagation()}>
              {f.dateTime(session.captured_at ?? session.created_at)}
            </Link>
          </span>
        );
      },
    }),
    col.display({
      id: 'object',
      header: t('columns.object'),
      cell: (info) => {
        const object = info.row.original.object;
        return object ? (
          <Link to={`/objects/${object.id}`} onClick={(event) => event.stopPropagation()}>
            {object.code} · {object.name}
          </Link>
        ) : (
          <span className="text-text-3">{t('unlinked')}</span>
        );
      },
    }),
    col.accessor('source', { header: t('columns.source'), cell: (info) => e('vision_source', info.getValue()) }),
    col.display({
      id: 'files',
      header: t('columns.files'),
      cell: (info) => (
        <span className="whitespace-nowrap tabular-nums">
          {t('filesCount', { files: info.row.original.assets_count, frames: info.row.original.frames_count })}
        </span>
      ),
    }),
    col.display({
      id: 'status',
      header: t('columns.status'),
      cell: (info) => <SessionStatusChips session={info.row.original} />,
    }),
    col.accessor('findings_count', {
      header: t('columns.findings'),
      cell: (info) => <span className="tabular-nums">{info.getValue()}</span>,
    }),
    col.accessor('reviewed_by_name', {
      header: t('columns.reviewer'),
      cell: (info) => info.getValue() ?? <span className="text-text-3">—</span>,
    }),
  ]);

  return (
    <>
      <PageHeader
        title={t('title')}
        subtitle={t('subtitle')}
        actions={
          <Button onClick={() => setCreating(true)}>
            <IconPlus />
            {t('create')}
          </Button>
        }
      />
      <div className="mb-3 grid max-w-xl gap-3 sm:grid-cols-2">
        <SelectInput
          label={t('filters.source')}
          data={options('vision_source', SOURCES)}
          value={source}
          clearable
          placeholder={t('filters.any')}
          onChange={(value) => setFilters({ source: value })}
        />
        <SelectInput
          label={t('filters.status')}
          data={options('vision_session_status', SESSION_STATUSES)}
          value={status}
          clearable
          placeholder={t('filters.any')}
          onChange={(value) => setFilters({ status: value })}
        />
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
          onPageChange={(index) => setParams((prev) => patchParams(prev, { page: index === 0 ? null : String(index + 1) }))}
          onRowClick={(session) => void navigate(`/vision/${session.id}`)}
          getRowId={(session) => String(session.id)}
          loading={query.isPending}
          fetching={query.isFetching && !query.isPending}
          emptyText={status || source ? t('emptyFiltered') : t('empty')}
        />
      )}
      {creating && <NewSessionDialog opened onClose={() => setCreating(false)} />}
    </>
  );
}
