import { Textarea } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { Panel } from '@/components/Panel';
import classes from './Sections.module.css';

interface Props {
  value: string;
  editable: boolean;
  onChange: (next: string) => void;
}

export function NoteSection({ value, editable, onChange }: Props) {
  const { t } = useTranslation('signals');
  return (
    <Panel title={t('sections.note')}>
      {editable ? (
        <Textarea
          aria-label={t('sections.note')}
          placeholder={t('note.placeholder')}
          value={value}
          onChange={(event) => onChange(event.currentTarget.value)}
          autosize
          minRows={3}
          maxRows={12}
        />
      ) : value ? (
        <p className={classes.multiline}>{value}</p>
      ) : (
        <p className={classes.inlineEmpty}>{t('note.none')}</p>
      )}
    </Panel>
  );
}
