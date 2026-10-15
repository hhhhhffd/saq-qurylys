import { Checkbox, Stack } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { Panel } from '@/components/Panel';
import { useEnum } from '@/i18n/useEnum';
import { MEASURES } from '../constants';
import type { SignalDraft } from '../useSignalDraft';
import classes from './Sections.module.css';

interface Props {
  value: SignalDraft['proposed_measures'];
  editable: boolean;
  onChange: (next: SignalDraft['proposed_measures']) => void;
}

export function ProposedMeasuresSection({ value, editable, onChange }: Props) {
  const { t } = useTranslation('signals');
  const e = useEnum();

  return (
    <Panel title={t('sections.proposed_measures')}>
      {editable ? (
        <Checkbox.Group
          value={value}
          onChange={(next) => onChange(MEASURES.filter((code) => next.includes(code)))}
          aria-label={t('sections.proposed_measures')}
        >
          <Stack gap="xs">
            {MEASURES.map((code) => (
              <Checkbox key={code} value={code} label={e('measure', code)} />
            ))}
          </Stack>
        </Checkbox.Group>
      ) : value.length === 0 ? (
        <p className={classes.inlineEmpty}>{t('proposedMeasures.none')}</p>
      ) : (
        <ul className={classes.list}>
          {value.map((code) => (
            <li key={code}>{e('measure', code)}</li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
