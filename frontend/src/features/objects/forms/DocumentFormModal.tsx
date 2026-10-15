import { useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { IconInfoCircle } from '@tabler/icons-react';
import { Controller, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useCreateDocument, useUpdateDocument } from '@/api/hooks/objects';
import type { CheckSource, CheckStatus, DocType, DocumentInput, ObjectDocument } from '@/api/types';
import { FileInput } from '@/components/form/FileInput';
import { SelectInput } from '@/components/form/SelectInput';
import { TextArea } from '@/components/form/TextArea';
import { TextInput } from '@/components/form/TextInput';
import { useEnumOptions } from '@/i18n/useEnum';
import { useAddDocumentEvidence } from './api';
import { DateField, FormDialog, FormFooter, FormGrid, fullWidth } from './fields';
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
    <FormDialog opened={opened} onClose={onClose} title={document ? t('document.editTitle') : t('document.createTitle')}>
      <DocumentForm objectId={objectId} document={document} onClose={onClose} />
    </FormDialog>
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
  // The file is not a form value: it is not validated by the schema, only its size is checked.
  const [file, setFile] = useState<File | null>(null);
  const fileError = fileTooLarge(file) ? t('validation.fileTooLarge', { size: MAX_FILE_MB }) : null;

  const [initialValues] = useState<DocumentFormValues>(() => ({
    doc_type: document?.doc_type ?? null,
    number: document?.number ?? '',
    issued_at: toDateValue(document?.issued_at),
    issuer: document?.issuer ?? '',
    check_status: document?.check_status ?? 'checking',
    check_source: document?.check_source ?? null,
    note: document?.note ?? '',
  }));

  const schema = useMemo(
    () =>
      z.object({
        doc_type: z.custom<DocType | null>().refine((value) => value !== null, tc('required')),
        number: z.string(),
        issued_at: z.string().nullable(),
        issuer: z.string(),
        check_status: z.custom<CheckStatus>(),
        check_source: z.custom<CheckSource | null>(),
        note: z.string(),
      }),
    [tc],
  );

  const {
    register,
    control,
    handleSubmit,
  } = useForm<DocumentFormValues>({ resolver: zodResolver(schema), defaultValues: initialValues });

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
      { doc_type: document.doc_type, ...toFields(initialValues) },
    );
    if (Object.keys(changes).length === 0) attachFile();
    else updateDocument.mutate({ id: document.id, data: changes }, { onSuccess: attachFile });
  };

  return (
    <form onSubmit={handleSubmit(submit)} noValidate>
      <div className="mb-3 flex items-start gap-2 rounded border border-border bg-surface-sunken p-3 text-sm text-text-2">
        <IconInfoCircle size={16} className="mt-px shrink-0 text-text-3" aria-hidden />
        {t('document.registryHint')}
      </div>
      <FormGrid>
        <Controller
          control={control}
          name="doc_type"
          render={({ field, fieldState }) => (
            <SelectInput
              className={fullWidth}
              label={t('document.docType')}
              placeholder={t('document.docTypePlaceholder')}
              data={enumOptions('doc_type', DOC_TYPES)}
              required
              value={field.value}
              onChange={(value) => value && field.onChange(value)}
              error={fieldState.error?.message}
            />
          )}
        />
        <TextInput label={t('document.number')} {...register('number')} />
        {/* A cleared date cannot be sent in a PATCH, so editing only allows replacing it. */}
        <Controller
          control={control}
          name="issued_at"
          render={({ field }) => (
            <DateField label={t('document.issuedAt')} clearable={!document} value={field.value} onChange={field.onChange} />
          )}
        />
        <TextInput className={fullWidth} label={t('document.issuer')} {...register('issuer')} />
        <Controller
          control={control}
          name="check_status"
          render={({ field }) => (
            <SelectInput
              label={t('document.checkStatus')}
              data={enumOptions('check_status', CHECK_STATUSES)}
              required
              value={field.value}
              onChange={(value) => value && field.onChange(value)}
            />
          )}
        />
        <Controller
          control={control}
          name="check_source"
          render={({ field }) => (
            <SelectInput
              label={t('document.checkSource')}
              placeholder={t('document.checkSourcePlaceholder')}
              data={enumOptions('check_source', CHECK_SOURCES)}
              clearable={!document}
              value={field.value}
              onChange={field.onChange}
            />
          )}
        />
        <TextArea className={fullWidth} label={t('document.note')} minRows={2} maxRows={6} {...register('note')} />
        <FileInput
          className={fullWidth}
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
      </FormGrid>
      <FormFooter
        loading={pending}
        onCancel={onClose}
        submitLabel={document ? tc('save') : tc('create')}
        submitDisabled={fileError !== null}
      />
    </form>
  );
}
