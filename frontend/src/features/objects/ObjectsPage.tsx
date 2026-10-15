import { useState } from 'react';
import { Button, SegmentedControl, TextInput, VisuallyHidden } from '@mantine/core';
import { useDebouncedCallback } from '@mantine/hooks';
import { IconChevronRight, IconPlus, IconSearch, IconUpload } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { useObjects } from '@/api/hooks/objects';
import type { ObjectRow } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { dataColumns } from '@/components/dataColumns';
import { DataTable } from '@/components/DataTable';
import { DemoBadge } from '@/components/DemoBadge';
import { ErrorBlock } from '@/components/QueryState';
import { PageHeader } from '@/components/PageHeader';
import { ZoneBadge, ZoneDot } from '@/components/Zone';
import { ZoneDisclaimer } from '@/components/ZoneDisclaimer';
import { useEnum, useKeyStatusLabel } from '@/i18n/useEnum';
import { ImportCsvModal } from './forms/ImportCsvModal';
import { ObjectFormModal } from './forms/ObjectFormModal';
import { ZONES, isZone, parseId, patchParams } from './list/filters';
import { TerritoryFilter } from './list/TerritoryFilter';
import classes from './ObjectsPage.module.css';

const PAGE_SIZE = 25;
const SEARCH_DEBOUNCE_MS = 300;

const col = dataColumns<ObjectRow>();

export function ObjectsPage() {
  const { t } = useTranslation('objects');
  const { t: common } = useTranslation();
  const e = useEnum();
  const keyStatus = useKeyStatusLabel();
  const navigate = useNavigate();
  const { canEditRegistry } = useAuth();
  const [params, setParams] = useSearchParams();
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  const q = params.get('q') ?? '';
  const zoneParam = params.get('zone');
  const zone = isZone(zoneParam) ? zoneParam : null;
  const territoryId = parseId(params.get('territory'));
  const districtId = parseId(params.get('district'));
  const pageIndex = (parseId(params.get('page')) ?? 1) - 1;
  const hasFilters = q !== '' || zone !== null || territoryId !== null || districtId !== null;

  // The input follows the URL (back/forward, reset) but keeps what is being typed until the debounce writes it.
  const [searchText, setSearchText] = useState(q);
  const [syncedQuery, setSyncedQuery] = useState(q);
  if (q !== syncedQuery) {
    setSyncedQuery(q);
    setSearchText(q);
  }
  const writeQuery = useDebouncedCallback((value: string) => {
    const next = value.trim();
    setSyncedQuery(next);
    setParams((prev) => patchParams(prev, { q: next || null, page: null }), { replace: true });
  }, SEARCH_DEBOUNCE_MS);

  const setFilters = (patch: Record<string, string | null>) =>
    setParams((prev) => patchParams(prev, { ...patch, page: null }));

  const query = useObjects({
    zone: zone ?? undefined,
    district_id: districtId ?? undefined,
    q: q || undefined,
    limit: PAGE_SIZE,
    offset: pageIndex * PAGE_SIZE,
  });

  const columns = col.columns([
    col.accessor('code', {
      header: t('list.columns.code'),
      cell: (info) => <span className="tnum">{info.getValue()}</span>,
    }),
    col.accessor('name', {
      header: t('list.columns.name'),
      cell: (info) => (
        <span className={classes.nameCell}>
          <Link to={`/objects/${info.row.original.id}`} onClick={(event) => event.stopPropagation()}>
            {info.getValue()}
          </Link>
          {info.row.original.is_demo && <DemoBadge />}
        </span>
      ),
    }),
    col.accessor('developer_name', {
      header: t('list.columns.developer'),
      cell: (info) => info.getValue() ?? common('noValue'),
    }),
    col.accessor('district_name', {
      header: t('list.columns.district'),
      cell: (info) => info.getValue() ?? common('noValue'),
    }),
    col.accessor('score', {
      header: t('list.columns.score'),
      cell: (info) => <span className="tnum">{info.getValue() ?? common('noValue')}</span>,
    }),
    col.accessor('zone', {
      header: t('list.columns.zone'),
      cell: (info) => <ZoneBadge zone={info.getValue()} />,
    }),
    col.display({
      id: 'key_status',
      header: t('list.columns.keyStatus'),
      cell: (info) => keyStatus(info.row.original.key_status, info.row.original.key_status_detail),
    }),
    col.display({
      id: 'open',
      header: () => <VisuallyHidden>{common('open')}</VisuallyHidden>,
      cell: () => <IconChevronRight size={16} className="faint" aria-hidden />,
    }),
  ]);

  return (
    <>
      <PageHeader
        title={t('list.title')}
        actions={
          canEditRegistry && (
            <>
              <Button variant="default" leftSection={<IconUpload size={16} />} onClick={() => setImportOpen(true)}>
                {t('list.importCsv')}
              </Button>
              <Button leftSection={<IconPlus size={16} />} onClick={() => setCreateOpen(true)}>
                {t('list.create')}
              </Button>
            </>
          )
        }
      />
      <div className={classes.filters}>
        <TextInput
          className={classes.search}
          aria-label={t('list.search')}
          placeholder={t('list.search')}
          leftSection={<IconSearch size={16} />}
          value={searchText}
          onChange={(event) => {
            setSearchText(event.currentTarget.value);
            writeQuery(event.currentTarget.value);
          }}
        />
        <SegmentedControl
          aria-label={t('list.zoneFilter')}
          value={zone ?? 'all'}
          onChange={(value) => setFilters({ zone: isZone(value) ? value : null })}
          data={[
            { value: 'all', label: common('all') },
            ...ZONES.map((item) => ({
              value: item,
              label: (
                <span className={classes.zoneOption}>
                  <ZoneDot zone={item} />
                  {e('zone', item)}
                </span>
              ),
            })),
          ]}
        />
        <TerritoryFilter
          territoryId={territoryId}
          districtId={districtId}
          onChange={({ territory, district }) =>
            setFilters({
              territory: territory === null ? null : String(territory),
              district: district === null ? null : String(district),
            })
          }
        />
        {hasFilters && (
          <Button
            variant="subtle"
            onClick={() => {
              writeQuery.cancel();
              setParams(new URLSearchParams());
            }}
          >
            {common('reset')}
          </Button>
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
          onPageChange={(next) => setParams((prev) => patchParams(prev, { page: next === 0 ? null : String(next + 1) }))}
          onRowClick={(row) => void navigate(`/objects/${row.id}`)}
          getRowId={(row) => String(row.id)}
          loading={query.isPending}
          fetching={query.isFetching && !query.isPending}
          emptyText={
            <>
              {t('list.empty')}
              <br />
              <span className="faint">{t('list.emptyHint')}</span>
            </>
          }
        />
      )}
      <ZoneDisclaimer className={classes.disclaimer} />
      {canEditRegistry && (
        <>
          <ObjectFormModal opened={createOpen} onClose={() => setCreateOpen(false)} />
          <ImportCsvModal opened={importOpen} onClose={() => setImportOpen(false)} kind="objects" />
        </>
      )}
    </>
  );
}
