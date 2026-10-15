import { useState } from 'react';
import { Button } from '@mantine/core';
import { IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useUsers } from '@/api/hooks/reference';
import type { AdminUser } from '@/api/types';
import { Chip } from '@/components/Chip';
import { dataColumns } from '@/components/dataColumns';
import { DataTable } from '@/components/DataTable';
import { QueryBoundary } from '@/components/QueryState';
import { useEnum } from '@/i18n/useEnum';
import { useTerritoryList } from '@/lib/territories';
import { ActionsHeader, EditButton, RowActions } from './RowActions';
import { SectionHeader } from './SectionHeader';
import { UserFormModal } from './UserFormModal';
import { territoryLabels } from './territoryTree';
import { usePagedRows } from './usePagedRows';
import classes from './AdminPage.module.css';

const PAGE_SIZE = 50;
const col = dataColumns<AdminUser>();

function UsersTable({ users, onEdit }: { users: AdminUser[]; onEdit: (user: AdminUser) => void }) {
  const { t } = useTranslation('admin');
  const e = useEnum();
  const { territories } = useTerritoryList();
  const labels = territoryLabels(territories);
  const { pageRows, pageIndex, setPageIndex } = usePagedRows(users, PAGE_SIZE);

  const columns = [
    col.display({
      id: 'username',
      header: t('users.columns.username'),
      cell: ({ row }) => <span className={classes.mono}>{row.original.username}</span>,
    }),
    col.display({ id: 'full_name', header: t('users.columns.fullName'), cell: ({ row }) => row.original.full_name }),
    col.display({
      id: 'role',
      header: t('users.columns.role'),
      cell: ({ row }) => <Chip>{e('role', row.original.role)}</Chip>,
    }),
    col.display({
      id: 'territory',
      header: t('users.columns.territory'),
      cell: ({ row }) => {
        const id = row.original.territory_id;
        return id === null ? t('wholeCountry') : (labels.get(id) ?? `#${id}`);
      },
    }),
    col.display({
      id: 'locale',
      header: t('users.columns.locale'),
      cell: ({ row }) => t(`locales.${row.original.locale}`),
    }),
    col.display({
      id: 'status',
      header: t('users.columns.status'),
      cell: ({ row }) =>
        row.original.is_active ? <Chip tone="green">{t('status.active')}</Chip> : <Chip>{t('status.inactive')}</Chip>,
    }),
    col.display({
      id: 'actions',
      header: ActionsHeader,
      cell: ({ row }) => (
        <RowActions>
          <EditButton label={t('editRow', { name: row.original.username })} onClick={() => onEdit(row.original)} />
        </RowActions>
      ),
    }),
  ];

  return (
    <DataTable
      columns={columns}
      data={pageRows}
      total={users.length}
      pageIndex={pageIndex}
      pageSize={PAGE_SIZE}
      onPageChange={setPageIndex}
      getRowId={(user) => String(user.id)}
      emptyText={t('users.empty')}
    />
  );
}

export function UsersSection() {
  const { t } = useTranslation('admin');
  const query = useUsers();
  // `{}` opens the modal in create mode, `{ user }` in edit mode.
  const [editing, setEditing] = useState<{ user?: AdminUser } | null>(null);

  return (
    <section>
      <SectionHeader
        title={t('users.title')}
        description={t('users.description')}
        actions={
          <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing({})}>
            {t('users.add')}
          </Button>
        }
      />
      <QueryBoundary query={query}>
        {(users) => <UsersTable users={users} onEdit={(user) => setEditing({ user })} />}
      </QueryBoundary>
      {editing && <UserFormModal user={editing.user} onClose={() => setEditing(null)} />}
    </section>
  );
}
