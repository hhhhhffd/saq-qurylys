import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useImportComplaints, useImportObjects } from '@/api/hooks/objects';
import type { ImportResult } from '@/api/types';
import { Chip } from '@/components/Chip';
import { FileInput } from '@/components/form/FileInput';
import { Button } from '@/components/ui/button';
import { DialogFooter } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { FormDialog, FormFooter } from './fields';
import { MAX_FILE_MB, fileTooLarge } from './utils';

export interface ImportCsvModalProps {
  opened: boolean;
  onClose: () => void;
  /** `POST /objects/import` or `POST /complaints/import` */
  kind: 'objects' | 'complaints';
}

/** Header columns the backend requires in each kind of file. */
const REQUIRED_COLUMNS = { objects: 'name, territory_code', complaints: 'object_code, received_at' } as const;
/** Optional complaint columns; `is_verified` marks an already checked complaint (R4 counts only those). */
const COMPLAINT_OPTIONAL_COLUMNS =
  'source, external_id, is_collective, signatories_count, summary, status, confirmed_payments, is_verified';

export function ImportCsvModal({ opened, onClose, kind }: ImportCsvModalProps) {
  const { t } = useTranslation('objectForms');
  return (
    <FormDialog opened={opened} onClose={onClose} title={t(`import.title.${kind}`)}>
      <ImportForm kind={kind} onClose={onClose} />
    </FormDialog>
  );
}

function ImportForm({ kind, onClose }: Omit<ImportCsvModalProps, 'opened'>) {
  const { t } = useTranslation('objectForms');
  const { t: tc } = useTranslation('common');
  const importObjects = useImportObjects();
  const importComplaints = useImportComplaints();
  const mutation = kind === 'objects' ? importObjects : importComplaints;
  const [file, setFile] = useState<File | null>(null);
  const fileError = fileTooLarge(file) ? t('validation.fileTooLarge', { size: MAX_FILE_MB }) : null;

  if (mutation.data) {
    return (
      <ImportOutcome
        result={mutation.data}
        onClose={onClose}
        onAnother={() => {
          mutation.reset();
          setFile(null);
        }}
      />
    );
  }

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        if (file && !fileError) mutation.mutate(file);
      }}
    >
      <FileInput
        label={t('import.file')}
        description={
          <>
            {t('import.hint', { columns: REQUIRED_COLUMNS[kind] })}
            {kind === 'complaints' && (
              <>
                <br />
                {t('import.optionalHint', { columns: COMPLAINT_OPTIONAL_COLUMNS })}
              </>
            )}
          </>
        }
        placeholder={tc('selectFile')}
        accept=".csv,text/csv"
        clearable
        required
        value={file}
        onChange={setFile}
        error={fileError}
      />
      <FormFooter
        loading={mutation.isPending}
        onCancel={onClose}
        submitLabel={t('import.submit')}
        submitDisabled={!file || fileError !== null}
      />
    </form>
  );
}

interface ImportOutcomeProps {
  result: ImportResult;
  onClose: () => void;
  onAnother: () => void;
}

function ImportOutcome({ result, onClose, onAnother }: ImportOutcomeProps) {
  const { t } = useTranslation('objectForms');
  const { t: tc } = useTranslation('common');
  const saved = result.created + result.updated;
  const failed = result.errors.length;

  let verdict: { tone: 'green' | 'yellow' | 'red'; label: string; text: string };
  if (failed === 0) {
    verdict = { tone: 'green', label: t('import.verdict.ok'), text: t('import.verdictText.ok') };
  } else if (saved > 0) {
    verdict = { tone: 'yellow', label: t('import.verdict.partial'), text: t('import.verdictText.partial') };
  } else {
    verdict = { tone: 'red', label: t('import.verdict.failed'), text: t('import.verdictText.failed') };
  }

  const stats = [
    { value: result.created, label: t('import.created') },
    { value: result.updated, label: t('import.updated') },
    { value: failed, label: t('import.failed') },
  ];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Chip tone={verdict.tone}>{verdict.label}</Chip>
        <p className="min-w-48 flex-1 text-sm text-text-2">{verdict.text}</p>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {stats.map((stat) => (
          <div key={stat.label} className="flex flex-col gap-0.5 rounded border border-border bg-surface px-3 py-2.5">
            <span className="font-heading text-2xl leading-tight font-bold tabular-nums">{stat.value}</span>
            <span className="text-xs text-text-2">{stat.label}</span>
          </div>
        ))}
      </div>
      {failed > 0 && (
        <div>
          <p className="mb-1.5 text-sm font-semibold">{t('import.errorsTitle')}</p>
          <div className="max-h-65 overflow-auto rounded border border-border bg-surface">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="sticky top-0 w-22 bg-surface">{t('import.row')}</TableHead>
                  <TableHead className="sticky top-0 bg-surface">{t('import.message')}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {result.errors.map((error, index) => (
                  <TableRow key={`${error.row}-${index}`}>
                    <TableCell className="tabular-nums">{error.row}</TableCell>
                    <TableCell className="h-auto whitespace-normal">{error.message}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
      <DialogFooter>
        <Button type="button" variant="secondary" onClick={onAnother}>
          {t('import.another')}
        </Button>
        <Button type="button" onClick={onClose}>
          {tc('close')}
        </Button>
      </DialogFooter>
    </div>
  );
}
