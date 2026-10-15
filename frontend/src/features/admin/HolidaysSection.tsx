import { useState } from 'react';
import { Select } from '@mantine/core';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { useDeleteHoliday, useHolidays } from '@/api/hooks/reference';
import type { Holiday } from '@/api/types';
import { Chip } from '@/components/Chip';
import { dataColumns } from '@/components/dataColumns';
import { DataTable } from '@/components/DataTable';
import { QueryBoundary } from '@/components/QueryState';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { confirmAction } from '@/lib/confirm';
import { HolidayForm } from './HolidayForm';
import { ActionsHeader, DeleteButton, RowActions } from './RowActions';
import { SectionHeader } from './SectionHeader';
import { usePagedRows } from './usePagedRows';
import classes from './AdminPage.module.css';

const PAGE_SIZE = 50;
const YEARS_AROUND = 2;
const col = dataColumns<Holiday>();

function HolidaysTable({ holidays, year }: { holidays: Holiday[]; year: number }) {
  const { t } = useTranslation('admin');
  const e = useEnum();
  const format = useFormat();
  const remove = useDeleteHoliday();
  const weekday = new Intl.DateTimeFormat(format.locale, { weekday: 'short', timeZone: 'UTC' });

  const days = holidays.filter((holiday) => holiday.day.startsWith(`${year}-`)).sort((a, b) => a.day.localeCompare(b.day));
  const { pageRows, pageIndex, setPageIndex } = usePagedRows(days, PAGE_SIZE);

  const confirmRemove = (holiday: Holiday) =>
    confirmAction({
      title: t('holidays.remove.title'),
      message: t('holidays.remove.message', { date: format.date(holiday.day), name: holiday.name }),
      confirmLabel: t('delete', { ns: 'common' }),
      danger: true,
      onConfirm: () => remove.mutate(holiday.day),
    });

  const columns = [
    col.display({
      id: 'date',
      header: t('holidays.columns.date'),
      cell: ({ row }) => <span className="tnum">{format.date(row.original.day)}</span>,
    }),
    col.display({
      id: 'weekday',
      header: t('holidays.columns.weekday'),
      cell: ({ row }) => <span className="muted">{weekday.format(new Date(`${row.original.day}T00:00:00Z`))}</span>,
    }),
    col.display({
      id: 'kind',
      header: t('holidays.columns.kind'),
      cell: ({ row }) => (
        <Chip tone={row.original.kind === 'workday' ? 'info' : 'neutral'}>{e('holiday_kind', row.original.kind)}</Chip>
      ),
    }),
    col.display({ id: 'name', header: t('holidays.columns.name'), cell: ({ row }) => row.original.name }),
    col.display({
      id: 'actions',
      header: ActionsHeader,
      cell: ({ row }) => (
        <RowActions>
          <DeleteButton
            label={t('deleteRow', { name: format.date(row.original.day) })}
            onClick={() => confirmRemove(row.original)}
          />
        </RowActions>
      ),
    }),
  ];

  return (
    <DataTable
      columns={columns}
      data={pageRows}
      total={days.length}
      pageIndex={pageIndex}
      pageSize={PAGE_SIZE}
      onPageChange={setPageIndex}
      getRowId={(holiday) => holiday.day}
      emptyText={t('holidays.empty', { year })}
    />
  );
}

export function HolidaysSection() {
  const { t } = useTranslation('admin');
  const query = useHolidays();
  const [currentYear] = useState(() => dayjs().year());
  const [year, setYear] = useState(currentYear);

  const years = new Set<number>([year]);
  for (let offset = -YEARS_AROUND; offset <= YEARS_AROUND; offset += 1) years.add(currentYear + offset);
  query.data?.forEach((holiday) => years.add(dayjs(holiday.day).year()));
  const yearOptions = [...years].sort((a, b) => a - b).map((value) => ({ value: String(value), label: String(value) }));

  return (
    <section>
      <SectionHeader
        title={t('holidays.title')}
        description={t('holidays.description')}
        actions={
          <Select
            aria-label={t('holidays.year')}
            data={yearOptions}
            value={String(year)}
            onChange={(value) => value && setYear(Number(value))}
            allowDeselect={false}
            w={110}
          />
        }
      />
      <QueryBoundary query={query}>
        {(holidays) => (
          <div className={classes.stack}>
            <HolidayForm existingDays={new Set(holidays.map((holiday) => holiday.day))} onAdded={setYear} />
            <HolidaysTable holidays={holidays} year={year} />
          </div>
        )}
      </QueryBoundary>
    </section>
  );
}
