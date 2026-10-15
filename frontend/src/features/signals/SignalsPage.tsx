import { useState } from 'react';
import { Button, Select } from '@mantine/core';
import { IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { useSignals } from '@/api/hooks/signals';
import type { SignalRow, SignalStatus } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { dataColumns } from '@/components/dataColumns';
import { DataTable } from '@/components/DataTable';
import { ErrorBlock } from '@/components/QueryState';
import { ObjectSelect } from '@/components/ObjectSelect';
import { PageHeader } from '@/components/PageHeader';
import { ZoneBadge } from '@/components/Zone';
import { ZoneDisclaimer } from '@/components/ZoneDisclaimer';
import { useEnum, useEnumOptions } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { PAGE_SIZE, SIGNAL_STATUSES } from './constants';
import { CreateSignalModal } from './CreateSignalModal';
import { DueInfo } from './DueInfo';
import { SignalStatusChip } from './SignalStatusChip';
import classes from './SignalsPage.module.css';

function parseStatus(value: string | null): SignalStatus | undefined {
  return SIGNAL_STATUSES.find((status) => status === value);
}

function parsePositiveInt(value: string | null): number | undefined {
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

const col = dataColumns<SignalRow>();

export function SignalsPage() {
  const { t } = useTranslation('signals');
  const { t: tc } = useTranslation();
  const { canManageSignals, isRecipient } = useAuth();
  const e = useEnum();
  const enumOptions = useEnumOptions();
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
        <Link to={`/signals/${info.row.original.id}`} onClick={(event) => event.stopPropagation()}>
          {info.getValue()}
        </Link>
      ),
    }),
    col.accessor('object_name', { header: t('list.columns.object') }),
    col.accessor('zone', {
      header: t('list.columns.zone'),
      cell: (info) => <ZoneBadge zone={info.getValue()} />,
    }),
    col.accessor('status', {
      header: t('list.columns.status'),
      cell: (info) => <SignalStatusChip status={info.getValue()} />,
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
      cell: (info) => <span className="tnum">{dateTime(info.getValue())}</span>,
    }),
  ]);

  let emptyText = t('list.empty.admin');
  if (hasFilters) emptyText = t('list.empty.filtered');
  else if (canManageSignals) emptyText = t('list.empty.manage');
  else if (isRecipient) emptyText = t('list.empty.recipient');

  return (
    <>
      <PageHeader
        title={tc('nav.signals')}
        subtitle={isRecipient ? t('list.subtitleRecipient') : t('list.subtitle')}
        actions={
          canManageSignals && (
            <Button leftSection={<IconPlus size={16} />} onClick={() => setCreateOpen(true)}>
              {t('list.create')}
            </Button>
          )
        }
      />
      <div className={classes.filters}>
        <Select
          label={t('list.filters.status')}
          placeholder={t('list.filters.statusPlaceholder')}
          data={enumOptions('signal_status', SIGNAL_STATUSES)}
          value={status ?? null}
          onChange={(next) => setParam({ status: next, page: null })}
          clearable
        />
        {!isRecipient && (
          <ObjectSelect
            label={t('list.filters.object')}
            placeholder={t('list.filters.objectPlaceholder')}
            value={objectId ?? null}
            onChange={(next) => setParam({ object_id: next === null ? null : String(next), page: null })}
          />
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
      <ZoneDisclaimer className={classes.disclaimer} />
      <CreateSignalModal opened={createOpen} onClose={() => setCreateOpen(false)} />
    </>
  );
}
