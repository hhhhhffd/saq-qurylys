import { useTranslation } from 'react-i18next';
import { NumberInput } from '@/components/form/NumberInput';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';

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
      className="w-24"
      value={factor.weight}
      onChange={factor.onWeight}
      min={WEIGHT_MIN}
      max={WEIGHT_MAX}
      allowDecimal={false}
      hideControls
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
      onCheckedChange={factor.onActive}
      aria-label={t('factors.activeLabel', { name: factor.name })}
    />
  );
}

export function SaveCell({ row }: CellProps) {
  const { t } = useTranslation();
  const factor = row.original;
  return (
    <div className="flex min-w-36 items-center justify-end gap-1">
      {factor.changed && (
        <>
          <Button size="sm" variant="ghost" onClick={factor.onReset} disabled={factor.saving}>
            {t('reset')}
          </Button>
          <Button size="sm" onClick={factor.onSave} disabled={!factor.valid} loading={factor.saving}>
            {t('save')}
          </Button>
        </>
      )}
    </div>
  );
}
