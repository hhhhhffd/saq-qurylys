import { useState } from 'react';
import { IconAlertCircle, IconFileOff, IconPencil, IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { readBreakdown, type CheckStatus, type DocType, type ObjectDetail, type ObjectDocument } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Chip, type ChipTone } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { EvidenceThumbs } from '@/components/evidence/EvidenceImage';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { cn } from '@/lib/utils';
import { DocumentFormModal } from '../forms/DocumentFormModal';
import { anchorId } from '@/components/risk/anchors';
import { anchorTargetClass, subTitleClass } from './styles';

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

const subLineClass = 'block text-xs text-text-3';
const cellClass = 'h-auto py-2 align-top whitespace-normal';

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
  // A confirmed guarantee or MIO permit is the legal basis; the other of the two is not a gap then (scenario C).
  const basisConfirmed = readBreakdown(object.latest_score)?.legal_basis_status === 'confirmed';
  const missing = DOC_TYPES.filter((type) => !object.documents.some((doc) => doc.doc_type === type));

  return (
    <Panel
      title={t('card.documents.title')}
      id="documents"
      flush
      actions={
        canEditRegistry && (
          <Button variant="secondary" size="sm" onClick={() => setModal({ opened: true })}>
            <IconPlus />
            {t('card.documents.add')}
          </Button>
        )
      }
    >
      {documents.length === 0 ? (
        <p className="px-4 pb-4 text-text-3">{t('card.documents.empty')}</p>
      ) : (
        <Table className="min-w-155">
          <TableHeader>
            <TableRow>
              <TableHead scope="col" className="pl-4">{t('card.documents.columns.document')}</TableHead>
              <TableHead scope="col">{t('card.documents.columns.issued')}</TableHead>
              <TableHead scope="col">{t('card.documents.columns.check')}</TableHead>
              <TableHead scope="col">{t('card.documents.columns.evidence')}</TableHead>
              {canEditRegistry && (
                <TableHead scope="col" className="pr-4">
                  <span className="sr-only">{t('actions', { ns: 'common' })}</span>
                </TableHead>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {documents.map((doc) => (
              <TableRow key={doc.id} id={anchorId('document', doc.id)} className={anchorTargetClass}>
                <TableCell className={cn(cellClass, 'pl-4')}>
                  <span className="font-semibold">{e('doc_type', doc.doc_type)}</span>
                  {doc.number && (
                    <span className={cn(subLineClass, 'tabular-nums')}>{t('card.documents.number', { value: doc.number })}</span>
                  )}
                  {doc.note && <span className={subLineClass}>{doc.note}</span>}
                </TableCell>
                <TableCell className={cellClass}>
                  {doc.issuer ?? '—'}
                  {doc.issued_at && <span className={cn(subLineClass, 'tabular-nums')}>{date(doc.issued_at)}</span>}
                </TableCell>
                <TableCell className={cellClass}>
                  <Chip tone={CHECK_TONE[doc.check_status]}>{e('check_status', doc.check_status)}</Chip>
                  {(doc.check_source || doc.checked_at) && (
                    <span className={cn(subLineClass, 'mt-1 tabular-nums')}>
                      {[e('check_source', doc.check_source), doc.checked_at && dateTime(doc.checked_at)]
                        .filter(Boolean)
                        .join(' · ')}
                    </span>
                  )}
                </TableCell>
                <TableCell className={cellClass}>
                  {doc.evidence.length > 0 ? <EvidenceThumbs evidence={doc.evidence} size={40} /> : '—'}
                </TableCell>
                {canEditRegistry && (
                  <TableCell className={cn(cellClass, 'pr-4')}>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t('card.documents.edit')}
                          onClick={() => setModal({ opened: true, document: doc })}
                        >
                          <IconPencil />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>{t('card.documents.edit')}</TooltipContent>
                    </Tooltip>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      {missing.length > 0 && (
        <div className="border-t border-border px-4 pt-3 pb-4">
          <h4 className={subTitleClass}>{t('card.documents.missingTitle')}</h4>
          <ul className="mt-2 flex flex-wrap gap-1.5">
            {missing.map((type) => {
              const key = KEY_DOC_TYPES.includes(type) && !basisConfirmed;
              return (
                <li
                  key={type}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-sm border border-dashed border-border-strong px-2.5 py-0.5 text-sm text-text-3',
                    key && 'border-solid border-zone-red bg-zone-red-bg text-zone-red-ink',
                  )}
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
