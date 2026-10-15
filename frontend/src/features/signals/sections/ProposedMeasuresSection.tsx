import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import { Panel } from '@/components/Panel';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { useEnum } from '@/i18n/useEnum';
import { MEASURES } from '../constants';
import type { SignalDraft } from '../useSignalDraft';

interface Props {
  value: SignalDraft['proposed_measures'];
  editable: boolean;
  onChange: (next: SignalDraft['proposed_measures']) => void;
}

export function ProposedMeasuresSection({ value, editable, onChange }: Props) {
  const { t } = useTranslation('signals');
  const e = useEnum();
  const groupId = useId();

  const toggle = (code: (typeof MEASURES)[number], checked: boolean) =>
    onChange(MEASURES.filter((item) => (item === code ? checked : value.includes(item))));

  return (
    <Panel title={t('sections.proposed_measures')}>
      {editable ? (
        <div role="group" aria-label={t('sections.proposed_measures')} className="flex flex-col gap-2">
          {MEASURES.map((code) => (
            <div key={code} className="flex items-center gap-2">
              <Checkbox id={`${groupId}-${code}`} checked={value.includes(code)} onCheckedChange={(checked) => toggle(code, checked === true)} />
              <Label htmlFor={`${groupId}-${code}`} className="text-sm text-text-2">
                {e('measure', code)}
              </Label>
            </div>
          ))}
        </div>
      ) : value.length === 0 ? (
        <p className="text-text-3">{t('proposedMeasures.none')}</p>
      ) : (
        <ul className="m-0 list-disc pl-4">
          {value.map((code) => (
            <li key={code}>{e('measure', code)}</li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
