import { type ReactNode } from 'react';
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react';
import { useTable, type RowData } from '@tanstack/react-table';
import { useTranslation } from 'react-i18next';
import { features, type DataColumn } from './dataColumns';
import { EmptyState } from './QueryState';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { cn } from '@/lib/utils';

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
    <div className="overflow-hidden rounded border border-border bg-surface">
      <Table>
        <TableHeader className="bg-surface-sunken">
          {table.getHeaderGroups().map((group) => (
            <TableRow key={group.id}>
              {group.headers.map((header) => (
                <TableHead key={header.id}>{header.isPlaceholder ? null : <table.FlexRender header={header} />}</TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody className={cn('transition-opacity', fetching && 'opacity-60')}>
          {loading
            ? Array.from({ length: SKELETON_ROWS }, (_, rowIndex) => (
                <TableRow key={rowIndex}>
                  {columns.map((_column, colIndex) => (
                    <TableCell key={colIndex}>
                      <Skeleton className="h-3.5" />
                    </TableCell>
                  ))}
                </TableRow>
              ))
            : table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  className={onRowClick ? 'cursor-pointer outline-none focus-visible:bg-hover active:bg-pressed' : undefined}
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
                    <TableCell key={cell.id}>
                      <table.FlexRender cell={cell} />
                    </TableCell>
                  ))}
                </TableRow>
              ))}
        </TableBody>
      </Table>
      {!loading && data.length === 0 && <EmptyState>{emptyText}</EmptyState>}
      <footer className="flex min-h-9 items-center justify-between gap-3 border-t border-border px-3 py-1 text-xs">
        <span className="text-text-3 tabular-nums">{t('pagination.range', { from, to, total })}</span>
        {pageCount > 1 && (
          <div className="flex items-center gap-2 text-text-2">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t('pagination.prev')}
              disabled={pageIndex === 0}
              onClick={() => onPageChange(pageIndex - 1)}
            >
              <IconChevronLeft />
            </Button>
            <span className="tabular-nums">{t('pagination.page', { page: pageIndex + 1, pages: pageCount })}</span>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t('pagination.next')}
              disabled={pageIndex >= pageCount - 1}
              onClick={() => onPageChange(pageIndex + 1)}
            >
              <IconChevronRight />
            </Button>
          </div>
        )}
      </footer>
    </div>
  );
}
