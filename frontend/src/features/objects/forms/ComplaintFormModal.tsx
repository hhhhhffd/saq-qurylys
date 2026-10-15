import { useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useCreateComplaint, useUpdateComplaint } from '@/api/hooks/objects';
import type { Complaint, ComplaintInput, ComplaintSource, ComplaintStatus } from '@/api/types';
import { NumberInput } from '@/components/form/NumberInput';
import { SelectInput } from '@/components/form/SelectInput';
import { SwitchInput } from '@/components/form/SwitchInput';
import { TextArea } from '@/components/form/TextArea';
import { TextInput } from '@/components/form/TextInput';
import { useEnumOptions } from '@/i18n/useEnum';
import { DateField, FormDialog, FormFooter, FormGrid, fullWidth } from './fields';
import { changedFields, toDateValue, today } from './utils';

export interface ComplaintFormModalProps {
  opened: boolean;
  onClose: () => void;
  objectId: number;
  /** edit mode when provided (PATCH /complaints/{id}), create mode otherwise */
  complaint?: Complaint;
}

interface ComplaintFormValues {
  received_at: string | null;
  source: ComplaintSource;
  external_id: string;
  is_collective: boolean;
  signatories_count: number | string;
  summary: string;
  status: ComplaintStatus;
  confirmed_payments: boolean;
  is_verified: boolean;
}

const SOURCES: ComplaintSource[] = ['eotinish', 'manual', 'other'];
const STATUSES: ComplaintStatus[] = ['new', 'in_review', 'closed'];
const MIN_COLLECTIVE_SIGNATORIES = 2;
const MAX_SIGNATORIES = 100_000;

function toInput(values: ComplaintFormValues): ComplaintInput | null {
  if (values.received_at === null) return null;
  const externalId = values.external_id.trim();
  return {
    received_at: values.received_at,
    source: values.source,
    // The backend rejects an empty external id and a PATCH cannot send null, so an empty one is left out.
    external_id: externalId || undefined,
    is_collective: values.is_collective,
    signatories_count:
      values.is_collective && typeof values.signatories_count === 'number' ? values.signatories_count : 1,
    summary: values.summary.trim(),
    status: values.status,
    confirmed_payments: values.confirmed_payments,
    is_verified: values.is_verified,
  };
}

export function ComplaintFormModal({ opened, onClose, objectId, complaint }: ComplaintFormModalProps) {
  const { t } = useTranslation('objectForms');
  return (
    <FormDialog opened={opened} onClose={onClose} title={complaint ? t('complaint.editTitle') : t('complaint.createTitle')}>
      <ComplaintForm objectId={objectId} complaint={complaint} onClose={onClose} />
    </FormDialog>
  );
}

interface ComplaintFormProps {
  objectId: number;
  complaint?: Complaint;
  onClose: () => void;
}

function ComplaintForm({ objectId, complaint, onClose }: ComplaintFormProps) {
  const { t } = useTranslation('objectForms');
  const { t: tc } = useTranslation('common');
  const enumOptions = useEnumOptions();
  const createComplaint = useCreateComplaint();
  const updateComplaint = useUpdateComplaint();

  const [initialValues] = useState<ComplaintFormValues>(() => ({
    received_at: complaint ? toDateValue(complaint.received_at) : today(),
    source: complaint?.source ?? 'manual',
    external_id: complaint?.external_id ?? '',
    is_collective: complaint?.is_collective ?? false,
    signatories_count: complaint?.is_collective ? complaint.signatories_count : MIN_COLLECTIVE_SIGNATORIES,
    summary: complaint?.summary ?? '',
    status: complaint?.status ?? 'new',
    confirmed_payments: complaint?.confirmed_payments ?? false,
    is_verified: complaint?.is_verified ?? false,
  }));

  const schema = useMemo(
    () =>
      z
        .object({
          received_at: z.string().nullable().refine(Boolean, tc('required')),
          source: z.custom<ComplaintSource>(),
          external_id: z.string(),
          is_collective: z.boolean(),
          signatories_count: z.union([z.number(), z.string()]),
          summary: z.string(),
          status: z.custom<ComplaintStatus>(),
          confirmed_payments: z.boolean(),
          is_verified: z.boolean(),
        })
        .superRefine((values, ctx) => {
          const count = values.signatories_count;
          const valid =
            typeof count === 'number' &&
            Number.isInteger(count) &&
            count >= MIN_COLLECTIVE_SIGNATORIES &&
            count <= MAX_SIGNATORIES;
          if (values.is_collective && !valid) {
            ctx.addIssue({
              code: 'custom',
              path: ['signatories_count'],
              message: t('validation.signatories', { min: MIN_COLLECTIVE_SIGNATORIES, max: MAX_SIGNATORIES }),
            });
          }
        }),
    [t, tc],
  );

  const {
    register,
    control,
    handleSubmit,
  } = useForm<ComplaintFormValues>({ resolver: zodResolver(schema), defaultValues: initialValues });
  const isCollective = useWatch({ control, name: 'is_collective' });

  const submit = (values: ComplaintFormValues) => {
    const input = toInput(values);
    if (!input) return;
    if (!complaint) {
      createComplaint.mutate({ objectId, data: input }, { onSuccess: onClose });
      return;
    }
    const initial = toInput(initialValues);
    const changes = initial ? changedFields(input, initial) : input;
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    updateComplaint.mutate({ id: complaint.id, data: changes }, { onSuccess: onClose });
  };

  return (
    <form onSubmit={handleSubmit(submit)} noValidate>
      <FormGrid>
        <Controller
          control={control}
          name="received_at"
          render={({ field, fieldState }) => (
            <DateField
              label={t('complaint.receivedAt')}
              required
              value={field.value}
              onChange={field.onChange}
              error={fieldState.error?.message}
            />
          )}
        />
        <Controller
          control={control}
          name="source"
          render={({ field }) => (
            <SelectInput
              label={t('complaint.source')}
              data={enumOptions('complaint_source', SOURCES)}
              required
              value={field.value}
              onChange={(value) => value && field.onChange(value)}
            />
          )}
        />
        <TextInput label={t('complaint.externalId')} {...register('external_id')} />
        <Controller
          control={control}
          name="status"
          render={({ field }) => (
            <SelectInput
              label={t('complaint.status')}
              data={enumOptions('complaint_status', STATUSES)}
              required
              value={field.value}
              onChange={(value) => value && field.onChange(value)}
            />
          )}
        />
        <Controller
          control={control}
          name="is_collective"
          render={({ field }) => (
            <SwitchInput
              className={fullWidth}
              label={t('complaint.isCollective')}
              checked={field.value}
              onCheckedChange={field.onChange}
            />
          )}
        />
        {isCollective && (
          <Controller
            control={control}
            name="signatories_count"
            render={({ field, fieldState }) => (
              <NumberInput
                className={fullWidth}
                label={t('complaint.signatories')}
                allowDecimal={false}
                allowNegative={false}
                hideControls
                required
                value={field.value}
                onChange={field.onChange}
                onBlur={field.onBlur}
                error={fieldState.error?.message}
              />
            )}
          />
        )}
        <TextArea className={fullWidth} label={t('complaint.summary')} minRows={3} maxRows={8} {...register('summary')} />
        <Controller
          control={control}
          name="confirmed_payments"
          render={({ field }) => (
            <SwitchInput
              className={fullWidth}
              label={t('complaint.confirmedPayments')}
              description={t('complaint.confirmedPaymentsHint')}
              checked={field.value}
              onCheckedChange={field.onChange}
            />
          )}
        />
        <Controller
          control={control}
          name="is_verified"
          render={({ field }) => (
            <SwitchInput
              className={fullWidth}
              label={t('complaint.isVerified')}
              description={t('complaint.isVerifiedHint')}
              checked={field.value}
              onCheckedChange={field.onChange}
            />
          )}
        />
      </FormGrid>
      <FormFooter
        loading={createComplaint.isPending || updateComplaint.isPending}
        onCancel={onClose}
        submitLabel={complaint ? tc('save') : tc('create')}
      />
    </form>
  );
}
