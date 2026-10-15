import { useTranslation } from 'react-i18next';
import { TextArea } from '@/components/form/TextArea';
import { Panel } from '@/components/Panel';

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
        <TextArea
          aria-label={t('sections.note')}
          placeholder={t('note.placeholder')}
          value={value}
          onChange={(event) => onChange(event.currentTarget.value)}
          minRows={3}
          maxRows={12}
        />
      ) : value ? (
        <p className="break-words whitespace-pre-wrap">{value}</p>
      ) : (
        <p className="text-text-3">{t('note.none')}</p>
      )}
    </Panel>
  );
}
