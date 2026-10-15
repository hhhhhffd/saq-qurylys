import { useState } from 'react';
import { Button, FileInput, Group, Modal, ScrollArea, SimpleGrid, Stack, Table, Text } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { useImportComplaints, useImportObjects } from '@/api/hooks/objects';
import type { ImportResult } from '@/api/types';
import { Chip } from '@/components/Chip';
import classes from './forms.module.css';
import { MAX_FILE_MB, fileTooLarge } from './utils';

export interface ImportCsvModalProps {
  opened: boolean;
  onClose: () => void;
  /** `POST /objects/import` or `POST /complaints/import` */
  kind: 'objects' | 'complaints';
}

/** Header columns the backend requires in each kind of file. */
const REQUIRED_COLUMNS = { objects: 'name, territory_code', complaints: 'object_code, received_at' } as const;

export function ImportCsvModal({ opened, onClose, kind }: ImportCsvModalProps) {
  const { t } = useTranslation('objectForms');
  return (
    <Modal opened={opened} onClose={onClose} title={t(`import.title.${kind}`)} size="lg" closeOnClickOutside={false}>
      {/* The form mounts together with the modal body, so every opening starts from an empty state. */}
      <ImportForm kind={kind} onClose={onClose} />
    </Modal>
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
      onSubmit={(event) => {
        event.preventDefault();
        if (file && !fileError) mutation.mutate(file);
      }}
    >
      <FileInput
        label={t('import.file')}
        description={t('import.hint', { columns: REQUIRED_COLUMNS[kind] })}
        placeholder={tc('selectFile')}
        accept=".csv,text/csv"
        clearable
        withAsterisk
        value={file}
        onChange={setFile}
        error={fileError}
      />
      <Group justify="flex-end" mt="lg">
        <Button variant="default" onClick={onClose} disabled={mutation.isPending}>
          {tc('cancel')}
        </Button>
        <Button type="submit" loading={mutation.isPending} disabled={!file || fileError !== null}>
          {t('import.submit')}
        </Button>
      </Group>
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

  return (
    <Stack gap="md">
      <Group gap="sm" align="center">
        <Chip tone={verdict.tone}>{verdict.label}</Chip>
        <Text size="sm" c="dimmed" style={{ flex: 1, minWidth: 200 }}>
          {verdict.text}
        </Text>
      </Group>
      <SimpleGrid cols={3}>
        <div className={classes.stat}>
          <span className={classes.statValue}>{result.created}</span>
          <span className={classes.statLabel}>{t('import.created')}</span>
        </div>
        <div className={classes.stat}>
          <span className={classes.statValue}>{result.updated}</span>
          <span className={classes.statLabel}>{t('import.updated')}</span>
        </div>
        <div className={classes.stat}>
          <span className={classes.statValue}>{failed}</span>
          <span className={classes.statLabel}>{t('import.failed')}</span>
        </div>
      </SimpleGrid>
      {failed > 0 && (
        <div>
          <Text size="sm" fw={600} mb={6}>
            {t('import.errorsTitle')}
          </Text>
          <ScrollArea.Autosize mah={260} className={classes.resultErrors}>
            <Table stickyHeader>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th w={90}>{t('import.row')}</Table.Th>
                  <Table.Th>{t('import.message')}</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {result.errors.map((error, index) => (
                  <Table.Tr key={`${error.row}-${index}`}>
                    <Table.Td>{error.row}</Table.Td>
                    <Table.Td>{error.message}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </ScrollArea.Autosize>
        </div>
      )}
      <Group justify="flex-end">
        <Button variant="default" onClick={onAnother}>
          {t('import.another')}
        </Button>
        <Button onClick={onClose}>{tc('close')}</Button>
      </Group>
    </Stack>
  );
}
