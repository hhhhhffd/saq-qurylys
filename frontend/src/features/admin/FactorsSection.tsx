import { useState } from 'react';
import { Stack, Text } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { useRiskFactors, useUpdateRiskFactor } from '@/api/hooks/reference';
import type { RiskFactor } from '@/api/types';
import { dataColumns } from '@/components/dataColumns';
import { DataTable } from '@/components/DataTable';
import { QueryBoundary } from '@/components/QueryState';
import { confirmAction } from '@/lib/confirm';
import { ActiveCell, SaveCell, WEIGHT_MAX, WEIGHT_MIN, WeightCell, type FactorRow } from './FactorCells';
import { FactorHistory } from './FactorHistory';
import { ActionsHeader } from './RowActions';
import { SectionHeader } from './SectionHeader';
import { useFactorLabels } from './useFactorLabels';
import classes from './AdminPage.module.css';

interface Draft {
  weight: number | string;
  isActive: boolean;
}

const col = dataColumns<FactorRow>();

function FactorsTable({ factors }: { factors: RiskFactor[] }) {
  const { t } = useTranslation('admin');
  const { t: tc } = useTranslation('common');
  const labels = useFactorLabels();
  const update = useUpdateRiskFactor();
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});

  const clearDraft = (code: string) =>
    setDrafts((current) => {
      const next = { ...current };
      delete next[code];
      return next;
    });

  const rows: FactorRow[] = [...factors]
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((factor) => {
      const saved: Draft = { weight: factor.weight, isActive: factor.is_active };
      const draft = drafts[factor.code] ?? saved;
      const name = labels.name(factor.code);
      const weightIsValid =
        typeof draft.weight === 'number' &&
        Number.isInteger(draft.weight) &&
        draft.weight >= WEIGHT_MIN &&
        draft.weight <= WEIGHT_MAX;

      const save = () => {
        const { weight, isActive } = draft;
        if (typeof weight !== 'number') return;
        const weightChanged = weight !== factor.weight;
        const activeChanged = isActive !== factor.is_active;
        confirmAction({
          title: t('factors.confirm.title', { name }),
          message: (
            <Stack gap={6}>
              <Text size="sm">{t('factors.confirm.message')}</Text>
              {weightChanged && (
                <Text size="sm" fw={600}>
                  {t('factors.confirm.weight', { from: factor.weight, to: weight })}
                </Text>
              )}
              {activeChanged && (
                <Text size="sm" fw={600}>
                  {t('factors.confirm.active', {
                    from: factor.is_active ? tc('yes') : tc('no'),
                    to: isActive ? tc('yes') : tc('no'),
                  })}
                </Text>
              )}
            </Stack>
          ),
          confirmLabel: tc('save'),
          onConfirm: () =>
            update.mutate(
              {
                code: factor.code,
                data: {
                  ...(weightChanged && { weight }),
                  ...(activeChanged && { is_active: isActive }),
                },
              },
              { onSuccess: () => clearDraft(factor.code) },
            ),
        });
      };

      return {
        code: factor.code,
        name,
        description: labels.description(factor.code),
        weight: draft.weight,
        isActive: draft.isActive,
        changed: draft.weight !== factor.weight || draft.isActive !== factor.is_active,
        valid: weightIsValid,
        saving: update.isPending && update.variables.code === factor.code,
        onWeight: (weight) => setDrafts((current) => ({ ...current, [factor.code]: { ...(current[factor.code] ?? saved), weight } })),
        onActive: (isActive) =>
          setDrafts((current) => ({ ...current, [factor.code]: { ...(current[factor.code] ?? saved), isActive } })),
        onSave: save,
        onReset: () => clearDraft(factor.code),
      };
    });

  const columns = [
    col.display({
      id: 'name',
      header: t('factors.columns.factor'),
      cell: ({ row }) => <strong>{row.original.name}</strong>,
    }),
    col.display({
      id: 'description',
      header: t('factors.columns.description'),
      cell: ({ row }) => <span className="muted">{row.original.description}</span>,
    }),
    col.display({ id: 'weight', header: t('factors.columns.weight'), cell: WeightCell }),
    col.display({ id: 'active', header: t('factors.columns.active'), cell: ActiveCell }),
    col.display({ id: 'save', header: ActionsHeader, cell: SaveCell }),
  ];

  return (
    <DataTable
      columns={columns}
      data={rows}
      total={rows.length}
      pageIndex={0}
      pageSize={Math.max(rows.length, 1)}
      onPageChange={() => undefined}
      getRowId={(row) => row.code}
      emptyText={t('factors.empty')}
    />
  );
}

export function FactorsSection() {
  const { t } = useTranslation('admin');
  const query = useRiskFactors();

  return (
    <div className={classes.stack}>
      <section>
        <SectionHeader title={t('factors.title')} description={t('factors.description')} />
        <QueryBoundary query={query}>{(factors) => <FactorsTable factors={factors} />}</QueryBoundary>
      </section>
      <FactorHistory />
    </div>
  );
}
