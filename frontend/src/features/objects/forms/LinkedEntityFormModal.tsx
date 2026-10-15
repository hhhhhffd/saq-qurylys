import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useCreateLinkedEntity } from '@/api/hooks/objects';
import type { LinkedEntityKind } from '@/api/types';
import { SelectInput } from '@/components/form/SelectInput';
import { TextArea } from '@/components/form/TextArea';
import { TextInput } from '@/components/form/TextInput';
import { useEnumOptions } from '@/i18n/useEnum';
import { FormDialog, FormFooter } from './fields';

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
    <FormDialog opened={opened} onClose={onClose} title={t('linkedEntity.createTitle')} wide={false}>
      <LinkedEntityForm objectId={objectId} onClose={onClose} />
    </FormDialog>
  );
}

function LinkedEntityForm({ objectId, onClose }: Omit<LinkedEntityFormModalProps, 'opened'>) {
  const { t } = useTranslation('objectForms');
  const { t: tc } = useTranslation('common');
  const enumOptions = useEnumOptions();
  const createLinkedEntity = useCreateLinkedEntity();

  const schema = useMemo(
    () =>
      z.object({
        kind: z.custom<LinkedEntityKind>(),
        value: z.string().trim().min(1, tc('required')),
        note: z.string(),
      }),
    [tc],
  );

  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<LinkedEntityFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { kind: 'phone', value: '', note: '' },
  });
  const kind = useWatch({ control, name: 'kind' });

  const submit = (values: LinkedEntityFormValues) => {
    createLinkedEntity.mutate(
      { objectId, data: { kind: values.kind, value: values.value.trim(), note: values.note.trim() || undefined } },
      { onSuccess: onClose },
    );
  };

  return (
    <form onSubmit={handleSubmit(submit)} noValidate className="flex flex-col gap-3">
      <Controller
        control={control}
        name="kind"
        render={({ field }) => (
          <SelectInput
            label={t('linkedEntity.kind')}
            data={enumOptions('linked_kind', KINDS)}
            required
            value={field.value}
            onChange={(value) => value && field.onChange(value)}
          />
        )}
      />
      <TextInput
        label={t('linkedEntity.value')}
        description={kind === 'phone' ? t('linkedEntity.phoneHint') : undefined}
        placeholder={kind === 'phone' ? '+7 701 123 45 67' : undefined}
        required
        autoFocus
        error={errors.value?.message}
        {...register('value')}
      />
      <TextArea label={t('linkedEntity.note')} minRows={2} maxRows={5} {...register('note')} />
      <FormFooter loading={createLinkedEntity.isPending} onCancel={onClose} submitLabel={tc('create')} />
    </form>
  );
}
