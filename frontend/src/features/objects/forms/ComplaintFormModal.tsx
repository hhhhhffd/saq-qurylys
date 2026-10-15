import { Modal, NumberInput, Select, SimpleGrid, Switch, Textarea, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { useCreateComplaint, useUpdateComplaint } from '@/api/hooks/objects';
import type { Complaint, ComplaintInput, ComplaintSource, ComplaintStatus } from '@/api/types';
import { useEnumOptions } from '@/i18n/useEnum';
import { DateField, FormFooter } from './fields';
import classes from './forms.module.css';
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
    <Modal
      opened={opened}
      onClose={onClose}
      title={complaint ? t('complaint.editTitle') : t('complaint.createTitle')}
      size="lg"
      closeOnClickOutside={false}
    >
      {/* The form mounts together with the modal body, so every opening starts from fresh values. */}
      <ComplaintForm objectId={objectId} complaint={complaint} onClose={onClose} />
    </Modal>
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

  const form = useForm<ComplaintFormValues>({
    initialValues: {
      received_at: complaint ? toDateValue(complaint.received_at) : today(),
      source: complaint?.source ?? 'manual',
      external_id: complaint?.external_id ?? '',
      is_collective: complaint?.is_collective ?? false,
      signatories_count: complaint?.is_collective ? complaint.signatories_count : MIN_COLLECTIVE_SIGNATORIES,
      summary: complaint?.summary ?? '',
      status: complaint?.status ?? 'new',
      confirmed_payments: complaint?.confirmed_payments ?? false,
      is_verified: complaint?.is_verified ?? false,
    },
    validate: {
      received_at: (value) => (value ? null : tc('required')),
      signatories_count: (value, values) => {
        if (!values.is_collective) return null;
        return typeof value === 'number' &&
          Number.isInteger(value) &&
          value >= MIN_COLLECTIVE_SIGNATORIES &&
          value <= MAX_SIGNATORIES
          ? null
          : t('validation.signatories', { min: MIN_COLLECTIVE_SIGNATORIES, max: MAX_SIGNATORIES });
      },
    },
  });

  const submit = (values: ComplaintFormValues) => {
    const input = toInput(values);
    if (!input) return;
    if (!complaint) {
      createComplaint.mutate({ objectId, data: input }, { onSuccess: onClose });
      return;
    }
    const initial = toInput(form.getInitialValues());
    const changes = initial ? changedFields(input, initial) : input;
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    updateComplaint.mutate({ id: complaint.id, data: changes }, { onSuccess: onClose });
  };

  return (
    <form onSubmit={form.onSubmit(submit)}>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <DateField label={t('complaint.receivedAt')} withAsterisk {...form.getInputProps('received_at')} />
        <Select
          label={t('complaint.source')}
          data={enumOptions('complaint_source', SOURCES)}
          allowDeselect={false}
          withAsterisk
          {...form.getInputProps('source')}
        />
        <TextInput label={t('complaint.externalId')} {...form.getInputProps('external_id')} />
        <Select
          label={t('complaint.status')}
          data={enumOptions('complaint_status', STATUSES)}
          allowDeselect={false}
          withAsterisk
          {...form.getInputProps('status')}
        />
        <Switch
          className={classes.full}
          label={t('complaint.isCollective')}
          {...form.getInputProps('is_collective', { type: 'checkbox' })}
        />
        {form.values.is_collective && (
          <NumberInput
            className={classes.full}
            label={t('complaint.signatories')}
            allowDecimal={false}
            allowNegative={false}
            hideControls
            withAsterisk
            {...form.getInputProps('signatories_count')}
          />
        )}
        <Textarea
          className={classes.full}
          label={t('complaint.summary')}
          autosize
          minRows={3}
          maxRows={8}
          {...form.getInputProps('summary')}
        />
        <Switch
          className={classes.full}
          label={t('complaint.confirmedPayments')}
          description={t('complaint.confirmedPaymentsHint')}
          {...form.getInputProps('confirmed_payments', { type: 'checkbox' })}
        />
        <Switch
          className={classes.full}
          label={t('complaint.isVerified')}
          description={t('complaint.isVerifiedHint')}
          {...form.getInputProps('is_verified', { type: 'checkbox' })}
        />
      </SimpleGrid>
      <FormFooter
        loading={createComplaint.isPending || updateComplaint.isPending}
        onCancel={onClose}
        submitLabel={complaint ? tc('save') : tc('create')}
      />
    </form>
  );
}
