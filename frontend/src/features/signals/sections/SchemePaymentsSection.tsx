import { useTranslation } from 'react-i18next';
import { Chip } from '@/components/Chip';
import { MultiSelect } from '@/components/form/MultiSelect';
import { TagsInput } from '@/components/form/TagsInput';
import { TextArea } from '@/components/form/TextArea';
import { KeyValue } from '@/components/KeyValue';
import { Panel } from '@/components/Panel';
import { useEnum, useEnumOptions } from '@/i18n/useEnum';
import { PAYMENT_SCHEMES } from '../constants';
import type { SignalDraft } from '../useSignalDraft';

interface Props {
  value: SignalDraft['scheme_payments'];
  editable: boolean;
  onChange: (next: SignalDraft['scheme_payments']) => void;
}

export function SchemePaymentsSection({ value, editable, onChange }: Props) {
  const { t } = useTranslation('signals');
  const e = useEnum();
  const enumOptions = useEnumOptions();

  if (editable) {
    return (
      <Panel title={t('sections.scheme_payments')}>
        <div className="flex flex-col gap-3.5">
          <MultiSelect
            label={t('schemePayments.paymentSchemes')}
            placeholder={t('schemePayments.paymentSchemesPlaceholder')}
            data={enumOptions('payment_scheme', PAYMENT_SCHEMES)}
            value={value.payment_schemes}
            onChange={(next) => onChange({ ...value, payment_schemes: PAYMENT_SCHEMES.filter((c) => next.includes(c)) })}
            clearable
          />
          <TagsInput
            label={t('schemePayments.contractTypes')}
            placeholder={t('schemePayments.contractTypesPlaceholder')}
            value={value.contract_types}
            onChange={(next) => onChange({ ...value, contract_types: next })}
          />
          <TextArea
            label={t('schemePayments.note')}
            placeholder={t('schemePayments.notePlaceholder')}
            value={value.confirmed_payments_note}
            onChange={(event) => onChange({ ...value, confirmed_payments_note: event.currentTarget.value })}
            minRows={3}
            maxRows={10}
          />
        </div>
      </Panel>
    );
  }

  return (
    <Panel title={t('sections.scheme_payments')}>
      <KeyValue
        columns={1}
        items={[
          {
            label: t('schemePayments.paymentSchemes'),
            value:
              value.payment_schemes.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {value.payment_schemes.map((scheme) => (
                    <Chip key={scheme}>{e('payment_scheme', scheme)}</Chip>
                  ))}
                </div>
              ),
          },
          {
            label: t('schemePayments.contractTypes'),
            value:
              value.contract_types.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {value.contract_types.map((type) => (
                    <Chip key={type} outline>
                      {type}
                    </Chip>
                  ))}
                </div>
              ),
          },
          {
            label: t('schemePayments.note'),
            value: value.confirmed_payments_note && (
              <p className="break-words whitespace-pre-wrap">{value.confirmed_payments_note}</p>
            ),
          },
        ]}
      />
    </Panel>
  );
}
