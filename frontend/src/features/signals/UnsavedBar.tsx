import { Button } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import classes from './UnsavedBar.module.css';

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
    <div className={classes.root} role="status">
      <div className={classes.text}>
        <strong>{t('unsaved.message')}</strong>
        {returned && <span className={classes.hint}>{t('unsaved.returnedHint')}</span>}
      </div>
      <div className={classes.buttons}>
        <Button variant="default" onClick={onDiscard} disabled={saving}>
          {t('unsaved.discard')}
        </Button>
        <Button onClick={onSave} loading={saving} disabled={!canSave}>
          {t('unsaved.save')}
        </Button>
      </div>
    </div>
  );
}
