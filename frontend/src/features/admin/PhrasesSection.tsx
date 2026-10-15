import { useState } from 'react';
import { Button, Select, TextInput } from '@mantine/core';
import { IconPlus, IconSearch } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { usePhrases } from '@/api/hooks/reference';
import type { Phrase } from '@/api/types';
import { Chip } from '@/components/Chip';
import { dataColumns } from '@/components/dataColumns';
import { DataTable } from '@/components/DataTable';
import { QueryBoundary } from '@/components/QueryState';
import { useEnum, useEnumOptions } from '@/i18n/useEnum';
import { PhraseFormModal } from './PhraseFormModal';
import { ActionsHeader, EditButton, RowActions } from './RowActions';
import { SectionHeader } from './SectionHeader';
import { PHRASE_CATEGORIES } from './phraseCategories';
import { usePagedRows } from './usePagedRows';
import classes from './AdminPage.module.css';

const PAGE_SIZE = 25;
const MAX_VISIBLE_VARIANTS = 4;
const col = dataColumns<Phrase>();

function PhrasesTable({ phrases, onEdit }: { phrases: Phrase[]; onEdit: (phrase: Phrase) => void }) {
  const { t } = useTranslation('admin');
  const e = useEnum();
  const enumOptions = useEnumOptions();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState<string | null>(null);

  const needle = search.trim().toLowerCase();
  const filtered = phrases.filter(
    (phrase) =>
      (category === null || phrase.category === category) &&
      (needle === '' ||
        phrase.text.toLowerCase().includes(needle) ||
        phrase.variants.some((variant) => variant.toLowerCase().includes(needle))),
  );
  const { pageRows, pageIndex, setPageIndex } = usePagedRows(filtered, PAGE_SIZE);
  const isFiltered = needle !== '' || category !== null;

  const columns = [
    col.display({
      id: 'text',
      header: t('phrases.columns.text'),
      cell: ({ row }) => <strong>{row.original.text}</strong>,
    }),
    col.display({
      id: 'variants',
      header: t('phrases.columns.variants'),
      cell: ({ row }) => {
        const { variants } = row.original;
        const hidden = variants.length - MAX_VISIBLE_VARIANTS;
        return (
          <div className={classes.chips}>
            {variants.slice(0, MAX_VISIBLE_VARIANTS).map((variant) => (
              <Chip key={variant} outline>
                {variant}
              </Chip>
            ))}
            {hidden > 0 && <Chip outline>{`+${hidden}`}</Chip>}
          </div>
        );
      },
    }),
    col.display({
      id: 'category',
      header: t('phrases.columns.category'),
      cell: ({ row }) => e('phrase_category', row.original.category),
    }),
    col.display({
      id: 'weight',
      header: t('phrases.columns.weight'),
      cell: ({ row }) => <span className="tnum">{row.original.weight}</span>,
    }),
    col.display({
      id: 'status',
      header: t('phrases.columns.active'),
      cell: ({ row }) =>
        row.original.is_active ? <Chip tone="green">{t('status.active')}</Chip> : <Chip>{t('status.inactive')}</Chip>,
    }),
    col.display({
      id: 'actions',
      header: ActionsHeader,
      cell: ({ row }) => (
        <RowActions>
          <EditButton label={t('editRow', { name: row.original.text })} onClick={() => onEdit(row.original)} />
        </RowActions>
      ),
    }),
  ];

  return (
    <>
      <div className={classes.toolbar}>
        <TextInput
          className={classes.toolbarSearch}
          label={t('phrases.search')}
          value={search}
          onChange={(event) => {
            setSearch(event.currentTarget.value);
            setPageIndex(0);
          }}
          leftSection={<IconSearch size={16} />}
        />
        <Select
          label={t('phrases.categoryFilter')}
          placeholder={t('phrases.allCategories')}
          data={enumOptions('phrase_category', PHRASE_CATEGORIES)}
          value={category}
          onChange={(value) => {
            setCategory(value);
            setPageIndex(0);
          }}
          clearable
        />
      </div>
      <DataTable
        columns={columns}
        data={pageRows}
        total={filtered.length}
        pageIndex={pageIndex}
        pageSize={PAGE_SIZE}
        onPageChange={setPageIndex}
        getRowId={(phrase) => String(phrase.id)}
        emptyText={isFiltered ? t('phrases.emptyFiltered') : t('phrases.empty')}
      />
    </>
  );
}

export function PhrasesSection() {
  const { t } = useTranslation('admin');
  const query = usePhrases();
  // `{}` opens the modal in create mode, `{ phrase }` in edit mode.
  const [editing, setEditing] = useState<{ phrase?: Phrase } | null>(null);

  return (
    <section>
      <SectionHeader
        title={t('phrases.title')}
        description={t('phrases.description')}
        actions={
          <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing({})}>
            {t('phrases.add')}
          </Button>
        }
      />
      <QueryBoundary query={query}>
        {(phrases) => <PhrasesTable phrases={phrases} onEdit={(phrase) => setEditing({ phrase })} />}
      </QueryBoundary>
      {editing && <PhraseFormModal phrase={editing.phrase} onClose={() => setEditing(null)} />}
    </section>
  );
}
