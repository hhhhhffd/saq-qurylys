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
      className="sticky bottom-4 z-10 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-lg border border-border-strong bg-surface-raised px-3 py-2 shadow-2"
    >
      <div className="flex min-w-0 flex-col text-sm">
        <strong>{t('unsaved.message')}</strong>
        {returned && <span className="text-xs text-text-3">{t('unsaved.returnedHint')}</span>}
      </div>
      <div className="flex gap-2">
        <Button variant="secondary" onClick={onDiscard} disabled={saving}>
          {t('unsaved.discard')}
        </Button>
        <Button onClick={onSave} loading={saving} disabled={!canSave}>
          {t('unsaved.save')}
        </Button>
      </div>
    </div>
  );
}
