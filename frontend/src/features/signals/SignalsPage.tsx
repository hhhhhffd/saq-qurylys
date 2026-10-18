import { useState } from 'react';
import { IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { useSignals } from '@/api/hooks/signals';
import type { SignalRow, SignalStatus } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { dataColumns } from '@/components/dataColumns';
import { DataTable } from '@/components/DataTable';
import { DemoBadge } from '@/components/DemoBadge';
import { ExportButton } from '@/components/ExportButton';
import { ErrorBlock } from '@/components/QueryState';
import { ObjectSelect } from '@/components/ObjectSelect';
import { PageHeader } from '@/components/PageHeader';
import { ZoneBadge } from '@/components/Zone';
import { ZoneDisclaimer } from '@/components/ZoneDisclaimer';
import { Button } from '@/components/ui/button';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { PAGE_SIZE, SIGNAL_STATUSES } from './constants';
import { CreateSignalModal } from './CreateSignalModal';
import { DueInfo } from './DueInfo';
import { SignalStatusChip } from './SignalStatusChip';

function parseStatus(value: string | null): SignalStatus | undefined {
  return SIGNAL_STATUSES.find((status) => status === value);
}

function parsePositiveInt(value: string | null): number | undefined {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

const col = dataColumns<SignalRow>();
const FILTER_STATUSES: SignalStatus[] = ['requires_confirmation', 'returned', 'responded', 'sent', 'closed'];
const RECIPIENT_FILTER_STATUSES: SignalStatus[] = ['sent', 'responded', 'closed'];

export function SignalsPage() {
  const { t } = useTranslation('signals');
  const { canManageSignals, isRecipient } = useAuth();
  const e = useEnum();
  const { dateTime } = useFormat();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [createOpen, setCreateOpen] = useState(false);

  const status = parseStatus(params.get('status'));
  // Recipients only see their own cards and cannot browse the registry, so the object filter is not offered to them.
  const objectId = isRecipient ? undefined : parsePositiveInt(params.get('object_id'));
  const pageIndex = (parsePositiveInt(params.get('page')) ?? 1) - 1;
  const hasFilters = status !== undefined || objectId !== undefined;

  const query = useSignals({ status, object_id: objectId, limit: PAGE_SIZE, offset: pageIndex * PAGE_SIZE });

  const setParam = (changes: Record<string, string | null>) => {
    setParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        for (const [key, value] of Object.entries(changes)) {
          if (value) next.set(key, value);
          else next.delete(key);
        }
        return next;
      },
      { replace: true },
    );
  };

  const columns = col.columns([
    col.accessor('number', {
      header: t('list.columns.number'),
      cell: (info) => (
        <Link to={`/signals/${info.row.original.id}`} className="text-link hover:underline" onClick={(event) => event.stopPropagation()}>
          {info.getValue()}
        </Link>
      ),
    }),
    col.accessor('object_name', {
      header: t('list.columns.object'),
      cell: (info) => (
        <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
          {info.getValue()}
          {info.row.original.is_demo && <DemoBadge />}
        </span>
      ),
    }),
    col.accessor('zone', {
      header: t('list.columns.zone'),
      cell: (info) => <ZoneBadge zone={info.getValue()} />,
    }),
    col.accessor('status', {
      header: t('list.columns.nextStep'),
      cell: (info) => {
        const rowStatus = info.getValue();
        const canAnswer =
          rowStatus === 'sent' &&
          (isRecipient || (canManageSignals && info.row.original.recipient === 'mio'));
        let nextStep: string;
        if (canAnswer) nextStep = t('list.next.recipient');
        else if (rowStatus === 'closed') nextStep = t('list.next.closed');
        else if (isRecipient && rowStatus === 'responded') nextStep = t('list.next.respondedRecipient');
        else if (isRecipient || !canManageSignals) nextStep = t('list.next.readOnly');
        else nextStep = t(`list.next.${rowStatus}`);
        return (
          <div className="flex min-w-36 flex-col items-start gap-1">
            <SignalStatusChip status={rowStatus} />
            <span className="text-xs text-text-2">{nextStep}</span>
          </div>
        );
      },
    }),
    col.accessor('recipient', {
      header: t('list.columns.recipient'),
      cell: (info) => e('recipient', info.getValue()) || '—',
    }),
    col.accessor('due_date', {
      header: t('list.columns.due'),
      cell: (info) => (
        <DueInfo
          dueDate={info.getValue()}
          status={info.row.original.status}
          isOverdue={info.row.original.is_overdue}
        />
      ),
    }),
    col.accessor('created_at', {
      header: t('list.columns.created'),
      cell: (info) => <span className="tabular-nums">{dateTime(info.getValue())}</span>,
    }),
  ]);

  let emptyText = t('list.empty.admin');
  if (hasFilters) emptyText = t('list.empty.filtered');
  else if (canManageSignals) emptyText = t('list.empty.manage');
  else if (isRecipient) emptyText = t('list.empty.recipient');

  const subtitle = isRecipient
    ? t('list.subtitleRecipient')
    : canManageSignals
      ? t('list.subtitleManage')
      : t('list.subtitleReadOnly');

  return (
    <>
      <PageHeader
        title={t('list.title')}
        subtitle={subtitle}
        actions={
          <>
            {!isRecipient && (
              <ExportButton path="/signals/export.xlsx" params={{ status, object_id: objectId }} filename="signals.xlsx" />
            )}
            {canManageSignals && (
              <Button className="min-h-11" onClick={() => setCreateOpen(true)}>
                <IconPlus />
                {t('list.create')}
              </Button>
            )}
          </>
        }
      />
      <div className="mb-4 grid gap-3">
        <div>
          <p className="mb-2 text-sm font-medium text-text">{t('list.filters.status')}</p>
          <div role="group" aria-label={t('list.filters.status')} className="flex flex-wrap gap-2">
            <Button
              variant={status === undefined ? 'default' : 'outline'}
              className="min-h-11"
              aria-pressed={status === undefined}
              onClick={() => setParam({ status: null, page: null })}
            >
              {t('list.filters.all')}
            </Button>
            {(isRecipient ? RECIPIENT_FILTER_STATUSES : FILTER_STATUSES).map((filterStatus) => (
              <Button
                key={filterStatus}
                variant={status === filterStatus ? 'default' : 'outline'}
                className="min-h-11"
                aria-pressed={status === filterStatus}
                onClick={() => setParam({ status: filterStatus, page: null })}
              >
                {t(`statusLabels.${filterStatus}`)}
              </Button>
            ))}
          </div>
        </div>
        {isRecipient ? (
          status !== undefined && (
            <div>
              <Button
                variant="secondary"
                className="min-h-11"
                onClick={() => setParam({ status: null, object_id: null, page: null })}
              >
                {t('list.filters.clear')}
              </Button>
            </div>
          )
        ) : (
          <div className="flex flex-wrap items-end gap-3">
            <ObjectSelect
              label={t('list.filters.object')}
              placeholder={t('list.filters.objectPlaceholder')}
              value={objectId ?? null}
              onChange={(next) => setParam({ object_id: next === null ? null : String(next), page: null })}
            />
            {hasFilters && (
              <Button
                variant="secondary"
                className="min-h-11"
                onClick={() => setParam({ status: null, object_id: null, page: null })}
              >
                {t('list.filters.clear')}
              </Button>
            )}
          </div>
        )}
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
          onPageChange={(next) => setParam({ page: next === 0 ? null : String(next + 1) })}
          onRowClick={(row) => void navigate(`/signals/${row.id}`)}
          getRowId={(row) => String(row.id)}
          loading={query.isPending}
          fetching={query.isFetching}
          emptyText={emptyText}
        />
      )}
      <ZoneDisclaimer className="mt-3" />
      <CreateSignalModal opened={createOpen} onClose={() => setCreateOpen(false)} />
    </>
  );
}
