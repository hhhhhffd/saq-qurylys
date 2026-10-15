import { Button, Switch, Tooltip, VisuallyHidden } from '@mantine/core';
import { IconRefresh } from '@tabler/icons-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useCollectSourceNow, useUpdateSourceAccount } from '@/api/hooks/ads';
import { useObject } from '@/api/hooks/objects';
import type { CollectorStatus, SourceAccount } from '@/api/types';
import { Chip } from '@/components/Chip';
import { dataColumns } from '@/components/dataColumns';
import { DataTable } from '@/components/DataTable';
import { isHttpUrl } from '@/features/ads/url';
import { usePagedRows } from '@/features/admin/usePagedRows';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { useTerritoryList } from '@/lib/territories';
import { collectorOf, isCollectorOn } from './collectors';
import classes from './SourcesPage.module.css';

const PAGE_SIZE = 50;
const col = dataColumns<SourceAccount>();

function BoundObject({ id }: { id: number | null }) {
  const object = useObject(id ?? 0, id !== null);
  if (id === null) return <span className="faint">—</span>;
  return <Link to={`/objects/${id}`}>{object.data ? `${object.data.code} · ${object.data.name}` : `#${id}`}</Link>;
}

interface Props {
  accounts: SourceAccount[];
  /** undefined while the states load: nothing can be collected yet */
  collectors: CollectorStatus[] | undefined;
}

export function SourcesTable({ accounts, collectors }: Props) {
  const { t } = useTranslation('sources');
  const e = useEnum();
  const { dateTime } = useFormat();
  const { territories } = useTerritoryList();
  const update = useUpdateSourceAccount();
  const collect = useCollectSourceNow();
  const { pageRows, pageIndex, setPageIndex } = usePagedRows(accounts, PAGE_SIZE);
  const territoryNames = new Map(territories.map((territory) => [territory.id, territory.name]));

  const collectBlocker = (account: SourceAccount): string | null => {
    const source = collectorOf(account);
    if (source === null) return t('collectUnsupported');
    return collectors && isCollectorOn(source, collectors) ? null : t('collectOff');
  };

  const columns = [
    col.display({
      id: 'platform',
      header: t('columns.platform'),
      cell: ({ row }) => <Chip>{e('platform', row.original.platform)}</Chip>,
    }),
    col.display({
      id: 'source',
      header: t('columns.source'),
      cell: ({ row }) => {
        const { handle, url } = row.original;
        return (
          <div className={classes.source}>
            <span className={classes.mono}>{handle}</span>
            {url &&
              (isHttpUrl(url) ? (
                <a className={classes.url} href={url} target="_blank" rel="noopener noreferrer" title={url}>
                  {url}
                </a>
              ) : (
                <span className={classes.url}>{url}</span>
              ))}
          </div>
        );
      },
    }),
    col.display({
      id: 'object',
      header: t('columns.object'),
      cell: ({ row }) => <BoundObject id={row.original.object_id} />,
    }),
    col.display({
      id: 'territory',
      header: t('columns.territory'),
      cell: ({ row }) => {
        const id = row.original.territory_id;
        return id === null ? '—' : (territoryNames.get(id) ?? `#${id}`);
      },
    }),
    col.display({
      id: 'watched',
      header: t('columns.watched'),
      cell: ({ row }) => (
        <Switch
          checked={row.original.is_watched}
          aria-label={t('watch', { name: row.original.handle })}
          disabled={update.isPending && update.variables?.id === row.original.id}
          onChange={(event) =>
            update.mutate({ id: row.original.id, data: { is_watched: event.currentTarget.checked } })
          }
        />
      ),
    }),
    col.display({
      id: 'lastCollected',
      header: t('columns.lastCollected'),
      cell: ({ row }) =>
        row.original.last_collected_at ? (
          <span className="tnum">{dateTime(row.original.last_collected_at)}</span>
        ) : (
          <span className="faint">{t('notCollected')}</span>
        ),
    }),
    col.display({
      id: 'lastError',
      header: t('columns.lastError'),
      cell: ({ row }) => {
        const { last_error: error, last_error_at: at } = row.original;
        if (!error) return <span className="faint">—</span>;
        return (
          <div className={classes.error}>
            <span className={classes.errorText} title={error}>
              {error}
            </span>
            <span className="faint tnum">{dateTime(at)}</span>
          </div>
        );
      },
    }),
    col.display({
      id: 'actions',
      header: () => <VisuallyHidden>{t('collectNow')}</VisuallyHidden>,
      cell: ({ row }) => {
        const blocker = collectBlocker(row.original);
        return (
          <div className={classes.actions}>
            <Tooltip label={blocker} disabled={blocker === null} multiline maw={260}>
              {/* A disabled button gets no pointer events, so the tooltip hangs on its wrapper. */}
              <span>
                <Button
                  variant="default"
                  size="compact-sm"
                  leftSection={<IconRefresh size={14} stroke={1.8} />}
                  disabled={blocker !== null}
                  loading={collect.isPending && collect.variables === row.original.id}
                  onClick={() => collect.mutate(row.original.id)}
                >
                  {t('collectNow')}
                </Button>
              </span>
            </Tooltip>
          </div>
        );
      },
    }),
  ];

  return (
    <DataTable
      columns={columns}
      data={pageRows}
      total={accounts.length}
      pageIndex={pageIndex}
      pageSize={PAGE_SIZE}
      onPageChange={setPageIndex}
      getRowId={(account) => String(account.id)}
      emptyText={t('empty')}
    />
  );
}
