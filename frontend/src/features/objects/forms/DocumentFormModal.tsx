import { useState } from 'react';
import { Alert, FileInput, Modal, Select, SimpleGrid, Textarea, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconInfoCircle } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useCreateDocument, useUpdateDocument } from '@/api/hooks/objects';
import type { CheckSource, CheckStatus, DocType, DocumentInput, ObjectDocument } from '@/api/types';
import { useEnumOptions } from '@/i18n/useEnum';
import { DateField, FormFooter } from './fields';
import classes from './forms.module.css';
import { useAddDocumentEvidence } from './api';
import { changedFields, fileTooLarge, MAX_FILE_MB, SCAN_ACCEPT, toDateValue } from './utils';

export interface DocumentFormModalProps {
  opened: boolean;
  onClose: () => void;
  objectId: number;
  /** edit mode when provided (PATCH /documents/{id}), create mode otherwise */
  document?: ObjectDocument;
}

interface DocumentFormValues {
  doc_type: DocType | null;
  number: string;
  issued_at: string | null;
  issuer: string;
  check_status: CheckStatus;
  check_source: CheckSource | null;
  note: string;
}

const DOC_TYPES: DocType[] = [
  'smr_notice',
  'psd',
  'expertise',
  'dsu_permit',
  'guarantee',
  'ddu_registration',
  'land_title',
];
const CHECK_STATUSES: CheckStatus[] = ['checking', 'confirmed', 'not_found'];
const CHECK_SOURCES: CheckSource[] = [
  'housing_portal',
  'kazreestr',
  'mio_registry',
  'cadastre',
  'eotinish',
  'manual',
  'other',
];

/** Empty text is sent as `''` (PATCH clears it; multipart create treats it as "not set"). */
function toFields(values: DocumentFormValues): Omit<DocumentInput, 'doc_type'> {
  return {
    number: values.number.trim(),
    issued_at: values.issued_at ?? undefined,
    issuer: values.issuer.trim(),
    check_status: values.check_status,
    check_source: values.check_source ?? undefined,
    note: values.note.trim(),
  };
}

export function DocumentFormModal({ opened, onClose, objectId, document }: DocumentFormModalProps) {
  const { t } = useTranslation('objectForms');
  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={document ? t('document.editTitle') : t('document.createTitle')}
      size="lg"
      closeOnClickOutside={false}
    >
      {/* The form mounts together with the modal body, so every opening starts from fresh values. */}
      <DocumentForm objectId={objectId} document={document} onClose={onClose} />
    </Modal>
  );
}

interface DocumentFormProps {
  objectId: number;
  document?: ObjectDocument;
  onClose: () => void;
}

function DocumentForm({ objectId, document, onClose }: DocumentFormProps) {
  const { t } = useTranslation('objectForms');
  const { t: tc } = useTranslation('common');
  const enumOptions = useEnumOptions();
  const createDocument = useCreateDocument();
  const updateDocument = useUpdateDocument();
  const addEvidence = useAddDocumentEvidence();
  const pending = createDocument.isPending || updateDocument.isPending || addEvidence.isPending;
  // The file stays out of the form state: Mantine clones form values and a cloned File is unusable.
  const [file, setFile] = useState<File | null>(null);
  const fileError = fileTooLarge(file) ? t('validation.fileTooLarge', { size: MAX_FILE_MB }) : null;

  const form = useForm<DocumentFormValues>({
    initialValues: {
      doc_type: document?.doc_type ?? null,
      number: document?.number ?? '',
      issued_at: toDateValue(document?.issued_at),
      issuer: document?.issuer ?? '',
      check_status: document?.check_status ?? 'checking',
      check_source: document?.check_source ?? null,
      note: document?.note ?? '',
    },
    validate: {
      doc_type: (value) => (value ? null : tc('required')),
    },
  });

  const submit = (values: DocumentFormValues) => {
    if (values.doc_type === null || fileError) return;
    const fields = toFields(values);
    if (!document) {
      createDocument.mutate({ objectId, data: { doc_type: values.doc_type, ...fields }, file }, { onSuccess: onClose });
      return;
    }
    // PATCH is JSON-only on the backend: a new screenshot goes to the evidence endpoint afterwards.
    const attachFile = () => {
      if (file) addEvidence.mutate({ id: document.id, file }, { onSuccess: onClose });
      else onClose();
    };
    const changes = changedFields(
      { doc_type: values.doc_type, ...fields },
      { doc_type: document.doc_type, ...toFields(form.getInitialValues()) },
    );
    if (Object.keys(changes).length === 0) attachFile();
    else updateDocument.mutate({ id: document.id, data: changes }, { onSuccess: attachFile });
  };

  return (
    <form onSubmit={form.onSubmit(submit)}>
      <Alert variant="light" color="gray" icon={<IconInfoCircle size={18} />} mb="md">
        {t('document.registryHint')}
      </Alert>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <Select
          className={classes.full}
          label={t('document.docType')}
          placeholder={t('document.docTypePlaceholder')}
          data={enumOptions('doc_type', DOC_TYPES)}
          allowDeselect={false}
          withAsterisk
          {...form.getInputProps('doc_type')}
        />
        <TextInput label={t('document.number')} {...form.getInputProps('number')} />
        {/* A cleared date cannot be sent in a PATCH, so editing only allows replacing it. */}
        <DateField label={t('document.issuedAt')} clearable={!document} {...form.getInputProps('issued_at')} />
        <TextInput className={classes.full} label={t('document.issuer')} {...form.getInputProps('issuer')} />
        <Select
          label={t('document.checkStatus')}
          data={enumOptions('check_status', CHECK_STATUSES)}
          allowDeselect={false}
          withAsterisk
          {...form.getInputProps('check_status')}
        />
        <Select
          label={t('document.checkSource')}
          placeholder={t('document.checkSourcePlaceholder')}
          data={enumOptions('check_source', CHECK_SOURCES)}
          clearable={!document}
          {...form.getInputProps('check_source')}
        />
        <Textarea
          className={classes.full}
          label={t('document.note')}
          autosize
          minRows={2}
          maxRows={6}
          {...form.getInputProps('note')}
        />
        <FileInput
          className={classes.full}
          label={t('document.file')}
          description={
            document && document.evidence.length > 0
              ? t('document.fileExisting', { n: document.evidence.length })
              : t('document.fileHint', { size: MAX_FILE_MB })
          }
          placeholder={t('document.filePlaceholder')}
          accept={SCAN_ACCEPT}
          clearable
          value={file}
          onChange={setFile}
          error={fileError}
        />
      </SimpleGrid>
      <FormFooter
        loading={pending}
        onCancel={onClose}
        submitLabel={document ? tc('save') : tc('create')}
        submitDisabled={fileError !== null}
      />
    </form>
  );
}
