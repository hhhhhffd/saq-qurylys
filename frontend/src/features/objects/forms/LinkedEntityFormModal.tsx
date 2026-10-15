import { Modal, Select, SimpleGrid, Textarea, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { useCreateLinkedEntity } from '@/api/hooks/objects';
import type { LinkedEntityKind } from '@/api/types';
import { useEnumOptions } from '@/i18n/useEnum';
import { FormFooter } from './fields';
import classes from './forms.module.css';

export interface LinkedEntityFormModalProps {
  opened: boolean;
  onClose: () => void;
  objectId: number;
}

interface LinkedEntityFormValues {
  kind: LinkedEntityKind;
  value: string;
  note: string;
}

const KINDS: LinkedEntityKind[] = ['ad_account', 'sales_office', 'phone', 'website', 'bank_details'];

export function LinkedEntityFormModal({ opened, onClose, objectId }: LinkedEntityFormModalProps) {
  const { t } = useTranslation('objectForms');
  return (
    <Modal opened={opened} onClose={onClose} title={t('linkedEntity.createTitle')} closeOnClickOutside={false}>
      {/* The form mounts together with the modal body, so every opening starts from fresh values. */}
      <LinkedEntityForm objectId={objectId} onClose={onClose} />
    </Modal>
  );
}

function LinkedEntityForm({ objectId, onClose }: Omit<LinkedEntityFormModalProps, 'opened'>) {
  const { t } = useTranslation('objectForms');
  const { t: tc } = useTranslation('common');
  const enumOptions = useEnumOptions();
  const createLinkedEntity = useCreateLinkedEntity();

  const form = useForm<LinkedEntityFormValues>({
    initialValues: { kind: 'phone', value: '', note: '' },
    validate: { value: (value) => (value.trim() ? null : tc('required')) },
  });

  const submit = (values: LinkedEntityFormValues) => {
    createLinkedEntity.mutate(
      { objectId, data: { kind: values.kind, value: values.value.trim(), note: values.note.trim() || undefined } },
      { onSuccess: onClose },
    );
  };

  return (
    <form onSubmit={form.onSubmit(submit)}>
      <SimpleGrid cols={1}>
        <Select
          label={t('linkedEntity.kind')}
          data={enumOptions('linked_kind', KINDS)}
          allowDeselect={false}
          withAsterisk
          {...form.getInputProps('kind')}
        />
        <TextInput
          label={t('linkedEntity.value')}
          description={form.values.kind === 'phone' ? t('linkedEntity.phoneHint') : undefined}
          placeholder={form.values.kind === 'phone' ? '+7 701 123 45 67' : undefined}
          withAsterisk
          data-autofocus
          {...form.getInputProps('value')}
        />
        <Textarea
          className={classes.full}
          label={t('linkedEntity.note')}
          autosize
          minRows={2}
          maxRows={5}
          {...form.getInputProps('note')}
        />
      </SimpleGrid>
      <FormFooter loading={createLinkedEntity.isPending} onCancel={onClose} submitLabel={tc('create')} />
    </form>
  );
}
