import { type ReactNode } from 'react';
import { ActionIcon, Skeleton } from '@mantine/core';
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react';
import { useTable, type RowData } from '@tanstack/react-table';
import { useTranslation } from 'react-i18next';
import { features, type DataColumn } from './dataColumns';
import { EmptyState } from './QueryState';
import classes from './DataTable.module.css';

interface Props<T extends RowData> {
  columns: DataColumn<T>[];
  data: T[];
  /** total rows on the server */
  total: number;
  /** zero-based page index */
  pageIndex: number;
  pageSize: number;
  onPageChange: (pageIndex: number) => void;
  onRowClick?: (row: T) => void;
  getRowId?: (row: T) => string;
  /** first load (no data yet) */
  loading?: boolean;
  /** refetching with previous data on screen */
  fetching?: boolean;
  emptyText?: ReactNode;
}

const SKELETON_ROWS = 6;

export function DataTable<T extends RowData>({
  columns,
  data,
  total,
  pageIndex,
  pageSize,
  onPageChange,
  onRowClick,
  getRowId,
  loading,
  fetching,
  emptyText,
}: Props<T>) {
  const { t } = useTranslation();
  const table = useTable({
    features,
    columns,
    data,
    getRowId: getRowId ? (row) => getRowId(row) : undefined,
    manualPagination: true,
    rowCount: total,
    state: { pagination: { pageIndex, pageSize } },
    onPaginationChange: (updater) => {
      const next = typeof updater === 'function' ? updater({ pageIndex, pageSize }) : updater;
      if (next.pageIndex !== pageIndex) onPageChange(next.pageIndex);
    },
  });

  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const from = total === 0 ? 0 : pageIndex * pageSize + 1;
  const to = Math.min(total, (pageIndex + 1) * pageSize);

  return (
    <div className={classes.root} data-fetching={fetching || undefined}>
      <div className={classes.scroll}>
        <table className={classes.table}>
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => (
                  <th key={header.id}>
                    {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: SKELETON_ROWS }, (_, rowIndex) => (
                  <tr key={rowIndex}>
                    {columns.map((_column, colIndex) => (
                      <td key={colIndex}>
                        <Skeleton height={14} radius="sm" />
                      </td>
                    ))}
                  </tr>
                ))
              : table.getRowModel().rows.map((row) => (
                  <tr
                    key={row.id}
                    className={onRowClick ? classes.clickable : undefined}
                    tabIndex={onRowClick ? 0 : undefined}
                    onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                    onKeyDown={
                      onRowClick
                        ? (event) => {
                            if (event.key === 'Enter' && event.target === event.currentTarget) onRowClick(row.original);
                          }
                        : undefined
                    }
                  >
                    {row.getAllCells().map((cell) => (
                      <td key={cell.id}>
                        <table.FlexRender cell={cell} />
                      </td>
                    ))}
                  </tr>
                ))}
          </tbody>
        </table>
        {!loading && data.length === 0 && <EmptyState>{emptyText}</EmptyState>}
      </div>
      <footer className={classes.footer}>
        <span className="tnum faint">{t('pagination.range', { from, to, total })}</span>
        {pageCount > 1 && (
          <div className={classes.pager}>
            <ActionIcon
              aria-label={t('pagination.prev')}
              disabled={pageIndex === 0}
              onClick={() => onPageChange(pageIndex - 1)}
            >
              <IconChevronLeft size={18} />
            </ActionIcon>
            <span className="tnum">{t('pagination.page', { page: pageIndex + 1, pages: pageCount })}</span>
            <ActionIcon
              aria-label={t('pagination.next')}
              disabled={pageIndex >= pageCount - 1}
              onClick={() => onPageChange(pageIndex + 1)}
            >
              <IconChevronRight size={18} />
            </ActionIcon>
          </div>
        )}
      </footer>
    </div>
  );
}
