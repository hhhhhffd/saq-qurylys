import { useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useCreateDeveloper, useUpdateDeveloper } from '@/api/hooks/objects';
import type { Developer, DeveloperInput } from '@/api/types';
import { TagsInput } from '@/components/form/TagsInput';
import { TextInput } from '@/components/form/TextInput';
import { FormDialog, FormFooter, FormGrid, fullWidth } from './fields';
import { changedFields, emptyToNull } from './utils';

export interface DeveloperFormModalProps {
  opened: boolean;
  onClose: () => void;
  /** edit mode when provided (PATCH /developers/{id}), create mode otherwise */
  developer?: Developer;
  /** called with the created/updated developer (used by ObjectFormModal to select a new developer) */
  onSaved?: (developer: Developer) => void;
}

interface DeveloperFormValues {
  bin: string;
  name: string;
  director: string;
  founders: string[];
  authorized_company: string;
  phones: string[];
}

const BIN_PATTERN = /^\d{12}$/;

/** Light check only; the server normalizes numbers to E.164 and rejects invalid ones. */
function looksLikePhone(value: string): boolean {
  const digits = value.replace(/\D/g, '');
  return /^\+?[\d\s().-]+$/.test(value) && digits.length >= 10 && digits.length <= 15;
}

/** Everything but the BIN, which the backend does not let anyone change after creation. */
function toEditableFields(values: DeveloperFormValues): Omit<DeveloperInput, 'bin'> {
  return {
    name: values.name.trim(),
    director: emptyToNull(values.director),
    founders: values.founders,
    authorized_company: emptyToNull(values.authorized_company),
    phones: values.phones,
  };
}

export function DeveloperFormModal({ opened, onClose, developer, onSaved }: DeveloperFormModalProps) {
  const { t } = useTranslation('objectForms');
  return (
    <FormDialog opened={opened} onClose={onClose} title={developer ? t('developer.editTitle') : t('developer.createTitle')}>
      <DeveloperForm developer={developer} onClose={onClose} onSaved={onSaved} />
    </FormDialog>
  );
}

interface DeveloperFormProps {
  developer?: Developer;
  onClose: () => void;
  onSaved?: (developer: Developer) => void;
}

function DeveloperForm({ developer, onClose, onSaved }: DeveloperFormProps) {
  const { t } = useTranslation('objectForms');
  const { t: tc } = useTranslation('common');
  const createDeveloper = useCreateDeveloper();
  const updateDeveloper = useUpdateDeveloper();
  const pending = createDeveloper.isPending || updateDeveloper.isPending;

  const [initialValues] = useState<DeveloperFormValues>(() => ({
    bin: developer?.bin ?? '',
    name: developer?.name ?? '',
    director: developer?.director ?? '',
    founders: developer?.founders ?? [],
    authorized_company: developer?.authorized_company ?? '',
    phones: developer?.phones ?? [],
  }));

  const schema = useMemo(
    () =>
      z.object({
        bin: z.string().refine((value) => BIN_PATTERN.test(value.trim()), t('validation.binDigits')),
        name: z.string().trim().min(1, tc('required')),
        director: z.string(),
        founders: z.array(z.string()),
        authorized_company: z.string(),
        phones: z.array(z.string()).refine((value) => value.every(looksLikePhone), t('validation.phoneInvalid')),
      }),
    [t, tc],
  );

  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<DeveloperFormValues>({ resolver: zodResolver(schema), defaultValues: initialValues });

  const handleSaved = (saved: Developer) => {
    onSaved?.(saved);
    onClose();
  };

  const submit = (values: DeveloperFormValues) => {
    if (!developer) {
      createDeveloper.mutate({ bin: values.bin.trim(), ...toEditableFields(values) }, { onSuccess: handleSaved });
      return;
    }
    const changes = changedFields(toEditableFields(values), toEditableFields(initialValues));
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    updateDeveloper.mutate({ id: developer.id, data: changes }, { onSuccess: handleSaved });
  };

  return (
    <form onSubmit={handleSubmit(submit)} noValidate>
      <FormGrid>
        <TextInput
          label={t('developer.bin')}
          description={developer ? t('developer.binLocked') : t('developer.binHint')}
          inputMode="numeric"
          maxLength={12}
          readOnly={developer !== undefined}
          required
          error={errors.bin?.message}
          {...register('bin')}
        />
        <TextInput
          label={t('developer.name')}
          required
          autoFocus={developer !== undefined}
          error={errors.name?.message}
          {...register('name')}
        />
        <TextInput label={t('developer.director')} {...register('director')} />
        <TextInput label={t('developer.authorizedCompany')} {...register('authorized_company')} />
        <Controller
          control={control}
          name="founders"
          render={({ field }) => (
            <TagsInput
              className={fullWidth}
              label={t('developer.founders')}
              description={t('developer.foundersHint')}
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
            />
          )}
        />
        <Controller
          control={control}
          name="phones"
          render={({ field, fieldState }) => (
            <TagsInput
              className={fullWidth}
              label={t('developer.phones')}
              description={t('developer.phonesHint')}
              placeholder="+7 701 123 45 67"
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
              error={fieldState.error?.message}
            />
          )}
        />
      </FormGrid>
      <FormFooter loading={pending} onCancel={onClose} submitLabel={developer ? tc('save') : tc('create')} />
    </form>
  );
}
