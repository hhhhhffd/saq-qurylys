import { useState } from 'react';
import { ActionIcon, Button, Tooltip, VisuallyHidden } from '@mantine/core';
import { IconAlertCircle, IconFileOff, IconPencil, IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import type { CheckStatus, DocType, ObjectDetail, ObjectDocument } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Chip, type ChipTone } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { EvidenceThumbs } from '@/components/evidence/EvidenceImage';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { DocumentFormModal } from '../forms/DocumentFormModal';
import { anchorId } from './anchors';
import classes from './Section.module.css';

const DOC_TYPES: DocType[] = [
  'dsu_permit',
  'guarantee',
  'smr_notice',
  'psd',
  'expertise',
  'ddu_registration',
  'land_title',
];
/** The documents the red zone rule depends on (SPEC 6.2). */
const KEY_DOC_TYPES: DocType[] = ['dsu_permit', 'guarantee'];

const CHECK_TONE: Record<CheckStatus, ChipTone> = { confirmed: 'green', not_found: 'red', checking: 'yellow' };

interface ModalState {
  opened: boolean;
  document?: ObjectDocument;
}

export function DocumentsSection({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const { date, dateTime } = useFormat();
  const { canEditRegistry } = useAuth();
  const [modal, setModal] = useState<ModalState>({ opened: false });

  const documents = [...object.documents].sort(
    (a, b) => DOC_TYPES.indexOf(a.doc_type) - DOC_TYPES.indexOf(b.doc_type) || a.id - b.id,
  );
  const missing = DOC_TYPES.filter((type) => !object.documents.some((doc) => doc.doc_type === type));

  return (
    <Panel
      title={t('card.documents.title')}
      id="documents"
      flush
      actions={
        canEditRegistry && (
          <Button
            variant="default"
            size="xs"
            leftSection={<IconPlus size={14} />}
            onClick={() => setModal({ opened: true })}
          >
            {t('card.documents.add')}
          </Button>
        )
      }
    >
      {documents.length === 0 ? (
        <p className={`${classes.muted} ${classes.pad}`}>{t('card.documents.empty')}</p>
      ) : (
        <div className={classes.tableWrap}>
          <table className={classes.table}>
            <thead>
              <tr>
                <th scope="col">{t('card.documents.columns.document')}</th>
                <th scope="col">{t('card.documents.columns.issued')}</th>
                <th scope="col">{t('card.documents.columns.check')}</th>
                <th scope="col">{t('card.documents.columns.evidence')}</th>
                {canEditRegistry && (
                  <th scope="col">
                    <VisuallyHidden>{t('actions', { ns: 'common' })}</VisuallyHidden>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id} id={anchorId('document', doc.id)} className={classes.target}>
                  <td>
                    <span className={classes.strong}>{e('doc_type', doc.doc_type)}</span>
                    {doc.number && (
                      <span className={`${classes.sub} tnum`}>{t('card.documents.number', { value: doc.number })}</span>
                    )}
                    {doc.note && <span className={classes.sub}>{doc.note}</span>}
                  </td>
                  <td>
                    {doc.issuer ?? '—'}
                    {doc.issued_at && <span className={`${classes.sub} tnum`}>{date(doc.issued_at)}</span>}
                  </td>
                  <td>
                    <Chip tone={CHECK_TONE[doc.check_status]}>{e('check_status', doc.check_status)}</Chip>
                    {(doc.check_source || doc.checked_at) && (
                      <span className={`${classes.sub} tnum`}>
                        {[e('check_source', doc.check_source), doc.checked_at && dateTime(doc.checked_at)]
                          .filter(Boolean)
                          .join(' · ')}
                      </span>
                    )}
                  </td>
                  <td>{doc.evidence.length > 0 ? <EvidenceThumbs evidence={doc.evidence} size={40} /> : '—'}</td>
                  {canEditRegistry && (
                    <td>
                      <Tooltip label={t('card.documents.edit')}>
                        <ActionIcon
                          variant="subtle"
                          color="gray"
                          aria-label={t('card.documents.edit')}
                          onClick={() => setModal({ opened: true, document: doc })}
                        >
                          <IconPencil size={16} />
                        </ActionIcon>
                      </Tooltip>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {missing.length > 0 && (
        <div className={classes.missing}>
          <h4 className={classes.subTitle}>{t('card.documents.missingTitle')}</h4>
          <ul className={classes.missingList}>
            {missing.map((type) => {
              const key = KEY_DOC_TYPES.includes(type);
              return (
                <li
                  key={type}
                  className={`${classes.missingItem} ${key ? classes.missingKey : ''}`}
                  title={key ? t('card.documents.keyMissing') : undefined}
                >
                  {key ? <IconAlertCircle size={14} aria-hidden /> : <IconFileOff size={14} aria-hidden />}
                  {e('doc_type', type)} · {t('card.documents.noRecord')}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {canEditRegistry && (
        <DocumentFormModal
          opened={modal.opened}
          onClose={() => setModal((state) => ({ ...state, opened: false }))}
          objectId={object.id}
          document={modal.document}
        />
      )}
    </Panel>
  );
}
