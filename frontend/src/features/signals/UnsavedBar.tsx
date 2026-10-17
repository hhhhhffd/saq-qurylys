import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';

interface Props {
  /** saving a returned card sends it back to confirmation */
  returned: boolean;
  saving: boolean;
  canSave: boolean;
  onSave: () => void;
  onDiscard: () => void;
}

export function UnsavedBar({ returned, saving, canSave, onSave, onDiscard }: Props) {
  const { t } = useTranslation('signals');
  return (
    <div
      role="status"
      className="sticky bottom-4 z-10 flex flex-col-reverse items-stretch justify-between gap-2 rounded-lg border border-border-strong bg-surface-raised px-3 py-2 shadow-2 sm:flex-row sm:items-center sm:gap-x-4"
    >
      <div className="flex min-w-0 flex-col text-sm">
        <strong>{t('unsaved.message')}</strong>
        {returned && <span className="text-xs text-text-3">{t('unsaved.returnedHint')}</span>}
        {!canSave && <span className="text-xs text-zone-red-ink">{t('unsaved.invalid')}</span>}
      </div>
      <div className="flex flex-wrap gap-2">
        <Button className="min-h-11 flex-1 sm:flex-none" variant="secondary" onClick={onDiscard} disabled={saving}>
          {t('unsaved.discard')}
        </Button>
        <Button className="min-h-11 flex-1 sm:flex-none" onClick={onSave} loading={saving} disabled={!canSave}>
          {t('unsaved.save')}
        </Button>
      </div>
    </div>
  );
}
