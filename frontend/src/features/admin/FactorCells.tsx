import { Button, NumberInput, Switch } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import classes from './AdminPage.module.css';

export const WEIGHT_MIN = -100;
export const WEIGHT_MAX = 100;

/** One factor with its unsaved edits and the handlers for them. */
export interface FactorRow {
  code: string;
  name: string;
  description: string;
  weight: number | string;
  isActive: boolean;
  changed: boolean;
  valid: boolean;
  saving: boolean;
  onWeight: (weight: number | string) => void;
  onActive: (isActive: boolean) => void;
  onSave: () => void;
  onReset: () => void;
}

interface CellProps {
  row: { original: FactorRow };
}

// These are module-level components on purpose: DataTable renders cell functions as components,
// so an inline cell would remount (and drop input focus) on every keystroke.

export function WeightCell({ row }: CellProps) {
  const { t } = useTranslation('admin');
  const factor = row.original;
  return (
    <NumberInput
      size="xs"
      w={92}
      value={factor.weight}
      onChange={factor.onWeight}
      min={WEIGHT_MIN}
      max={WEIGHT_MAX}
      allowDecimal={false}
      error={!factor.valid}
      aria-label={t('factors.weightLabel', { name: factor.name })}
    />
  );
}

export function ActiveCell({ row }: CellProps) {
  const { t } = useTranslation('admin');
  const factor = row.original;
  return (
    <Switch
      checked={factor.isActive}
      onChange={(event) => factor.onActive(event.currentTarget.checked)}
      aria-label={t('factors.activeLabel', { name: factor.name })}
    />
  );
}

export function SaveCell({ row }: CellProps) {
  const { t } = useTranslation();
  const factor = row.original;
  return (
    <div className={classes.saveCell}>
      {factor.changed && (
        <>
          <Button size="xs" variant="subtle" color="gray" onClick={factor.onReset} disabled={factor.saving}>
            {t('reset')}
          </Button>
          <Button size="xs" onClick={factor.onSave} disabled={!factor.valid} loading={factor.saving}>
            {t('save')}
          </Button>
        </>
      )}
    </div>
  );
}
