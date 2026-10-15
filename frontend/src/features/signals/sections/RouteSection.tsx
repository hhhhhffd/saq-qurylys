import { useTranslation } from 'react-i18next';
import type { SignalDetail } from '@/api/types';
import { NumberInput } from '@/components/form/NumberInput';
import { SelectInput } from '@/components/form/SelectInput';
import { KeyValue } from '@/components/KeyValue';
import { Panel } from '@/components/Panel';
import { useEnum, useEnumOptions } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { DueInfo } from '../DueInfo';
import { MAX_REVIEW_DAYS, RECIPIENTS } from '../constants';
import type { SignalDraft } from '../useSignalDraft';

interface Props {
  detail: SignalDetail;
  value: Pick<SignalDraft, 'recipient' | 'review_days'>;
  editable: boolean;
  onChange: (patch: Partial<Pick<SignalDraft, 'recipient' | 'review_days'>>) => void;
}

export function RouteSection({ detail, value, editable, onChange }: Props) {
  const { t } = useTranslation('signals');
  const e = useEnum();
  const enumOptions = useEnumOptions();
  const { dateTime } = useFormat();

  if (editable) {
    return (
      <Panel title={t('sections.route')}>
        <div className="flex flex-col gap-3.5">
          <SelectInput
            label={t('route.recipient')}
            placeholder={t('route.recipientPlaceholder')}
            data={enumOptions('recipient', RECIPIENTS)}
            value={value.recipient}
            onChange={(next) => onChange({ recipient: RECIPIENTS.find((code) => code === next) ?? null })}
          />
          <NumberInput
            label={t('route.reviewDays')}
            value={value.review_days}
            onChange={(next) => onChange({ review_days: typeof next === 'number' ? next : '' })}
            min={1}
            max={MAX_REVIEW_DAYS}
            allowDecimal={false}
            allowNegative={false}
            error={value.review_days === '' ? t('route.reviewDaysRequired') : undefined}
          />
          <p className="text-xs text-text-3">{t('route.hint')}</p>
        </div>
      </Panel>
    );
  }

  return (
    <Panel title={t('sections.route')}>
      <KeyValue
        columns={1}
        items={[
          { label: t('route.recipient'), value: e('recipient', value.recipient) },
          {
            label: t('detail.fields.reviewDays'),
            value: value.review_days === '' ? null : t('reviewDays', { count: value.review_days }),
          },
          { label: t('route.sentAt'), value: detail.sent_at && dateTime(detail.sent_at) },
          {
            label: t('route.dueDate'),
            value: detail.due_date && (
              <DueInfo dueDate={detail.due_date} status={detail.status} isOverdue={detail.is_overdue} />
            ),
          },
        ]}
      />
    </Panel>
  );
}
