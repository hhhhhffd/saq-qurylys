import { Modal, SimpleGrid, TagsInput, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { useCreateDeveloper, useUpdateDeveloper } from '@/api/hooks/objects';
import type { Developer, DeveloperInput } from '@/api/types';
import { FormFooter } from './fields';
import classes from './forms.module.css';
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
    <Modal
      opened={opened}
      onClose={onClose}
      title={developer ? t('developer.editTitle') : t('developer.createTitle')}
      size="lg"
      closeOnClickOutside={false}
    >
      {/* The form mounts together with the modal body, so every opening starts from fresh values. */}
      <DeveloperForm developer={developer} onClose={onClose} onSaved={onSaved} />
    </Modal>
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

  const form = useForm<DeveloperFormValues>({
    initialValues: {
      bin: developer?.bin ?? '',
      name: developer?.name ?? '',
      director: developer?.director ?? '',
      founders: developer?.founders ?? [],
      authorized_company: developer?.authorized_company ?? '',
      phones: developer?.phones ?? [],
    },
    validate: {
      bin: (value) => (BIN_PATTERN.test(value.trim()) ? null : t('validation.binDigits')),
      name: (value) => (value.trim() ? null : tc('required')),
      phones: (value) => (value.every(looksLikePhone) ? null : t('validation.phoneInvalid')),
    },
  });

  const handleSaved = (saved: Developer) => {
    onSaved?.(saved);
    onClose();
  };

  const submit = (values: DeveloperFormValues) => {
    if (!developer) {
      createDeveloper.mutate({ bin: values.bin.trim(), ...toEditableFields(values) }, { onSuccess: handleSaved });
      return;
    }
    const changes = changedFields(toEditableFields(values), toEditableFields(form.getInitialValues()));
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    updateDeveloper.mutate({ id: developer.id, data: changes }, { onSuccess: handleSaved });
  };

  return (
    <form onSubmit={form.onSubmit(submit)}>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <TextInput
          label={t('developer.bin')}
          description={developer ? t('developer.binLocked') : t('developer.binHint')}
          inputMode="numeric"
          maxLength={12}
          readOnly={developer !== undefined}
          withAsterisk
          data-autofocus={developer ? undefined : true}
          {...form.getInputProps('bin')}
        />
        <TextInput
          label={t('developer.name')}
          withAsterisk
          data-autofocus={developer ? true : undefined}
          {...form.getInputProps('name')}
        />
        <TextInput label={t('developer.director')} {...form.getInputProps('director')} />
        <TextInput label={t('developer.authorizedCompany')} {...form.getInputProps('authorized_company')} />
        <TagsInput
          className={classes.full}
          label={t('developer.founders')}
          description={t('developer.foundersHint')}
          {...form.getInputProps('founders')}
        />
        <TagsInput
          className={classes.full}
          label={t('developer.phones')}
          description={t('developer.phonesHint')}
          placeholder="+7 701 123 45 67"
          {...form.getInputProps('phones')}
        />
      </SimpleGrid>
      <FormFooter
        loading={pending}
        onCancel={onClose}
        submitLabel={developer ? tc('save') : tc('create')}
      />
    </form>
  );
}
