import { useState } from 'react';
import { IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useTerritories } from '@/api/hooks/reference';
import type { Territory } from '@/api/types';
import { Chip } from '@/components/Chip';
import { dataColumns } from '@/components/dataColumns';
import { DataTable } from '@/components/DataTable';
import { QueryBoundary } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { useEnum } from '@/i18n/useEnum';
import { toLatLon } from '@/lib/geo';
import { ActionsHeader, EditButton, RowActions } from './RowActions';
import { SectionHeader } from './SectionHeader';
import { TerritoryFormModal } from './TerritoryFormModal';
import { territoryRows, type TerritoryRow } from './territoryTree';
import { usePagedRows } from './usePagedRows';

const PAGE_SIZE = 50;
const INDENT_PX = 20;
const col = dataColumns<TerritoryRow>();

function TerritoriesTable({ tree, onEdit }: { tree: Territory[]; onEdit: (territory: Territory) => void }) {
  const { t } = useTranslation('admin');
  const e = useEnum();
  const rows = territoryRows(tree);
  const { pageRows, pageIndex, setPageIndex } = usePagedRows(rows, PAGE_SIZE);

  const columns = [
    col.display({
      id: 'name',
      header: t('territories.columns.name'),
      cell: ({ row }) => (
        <span style={{ paddingInlineStart: row.original.depth * INDENT_PX }}>
          {row.original.depth === 0 ? <strong>{row.original.territory.name}</strong> : row.original.territory.name}
        </span>
      ),
    }),
    col.display({
      id: 'level',
      header: t('territories.columns.level'),
      cell: ({ row }) => <Chip>{e('territory_level', row.original.territory.level)}</Chip>,
    }),
    col.display({
      id: 'code',
      header: t('territories.columns.code'),
      cell: ({ row }) => <span className="font-mono text-xs">{row.original.territory.code}</span>,
    }),
    col.display({
      id: 'timezone',
      header: t('territories.columns.timezone'),
      cell: ({ row }) => row.original.territory.timezone,
    }),
    col.display({
      id: 'center',
      header: t('territories.columns.center'),
      cell: ({ row }) => {
        const center = toLatLon(row.original.territory);
        return <span className="text-text-3 tabular-nums">{center ? `${center.lat.toFixed(4)}, ${center.lon.toFixed(4)}` : '—'}</span>;
      },
    }),
    col.display({
      id: 'actions',
      header: ActionsHeader,
      cell: ({ row }) => (
        <RowActions>
          <EditButton
            label={t('editRow', { name: row.original.territory.name })}
            onClick={() => onEdit(row.original.territory)}
          />
        </RowActions>
      ),
    }),
  ];

  return (
    <DataTable
      columns={columns}
      data={pageRows}
      total={rows.length}
      pageIndex={pageIndex}
      pageSize={PAGE_SIZE}
      onPageChange={setPageIndex}
      getRowId={(row) => String(row.territory.id)}
      emptyText={t('territories.empty')}
    />
  );
}

export function TerritoriesSection() {
  const { t } = useTranslation('admin');
  const query = useTerritories();
  // `{}` opens the modal in create mode, `{ territory }` in edit mode.
  const [editing, setEditing] = useState<{ territory?: Territory } | null>(null);

  return (
    <section>
      <SectionHeader
        title={t('territories.title')}
        description={t('territories.description')}
        actions={
          <Button onClick={() => setEditing({})}>
            <IconPlus />
            {t('territories.add')}
          </Button>
        }
      />
      <QueryBoundary query={query}>
        {(tree) => <TerritoriesTable tree={tree} onEdit={(territory) => setEditing({ territory })} />}
      </QueryBoundary>
      {editing && <TerritoryFormModal territory={editing.territory} onClose={() => setEditing(null)} />}
    </section>
  );
}
