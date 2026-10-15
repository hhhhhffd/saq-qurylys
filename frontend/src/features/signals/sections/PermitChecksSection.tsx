import { useTranslation } from 'react-i18next';
import type { CheckStatus, SignalSections } from '@/api/types';
import { Chip, type ChipTone } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { EvidenceList } from './EvidenceList';

const CHECK_TONE: Record<CheckStatus, ChipTone> = {
  confirmed: 'green',
  checking: 'yellow',
  not_found: 'red',
};

export function PermitChecksSection({ items }: { items: SignalSections['permit_checks'] }) {
  const { t } = useTranslation('signals');
  const e = useEnum();
  const { date } = useFormat();
  return (
    <Panel title={t('sections.permit_checks')} flush>
      {items.length === 0 ? (
        <p className="px-3 py-2.5 text-text-3">{t('sections.empty')}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t('permitChecks.docType')}</TableHead>
              <TableHead>{t('permitChecks.number')}</TableHead>
              <TableHead>{t('permitChecks.source')}</TableHead>
              <TableHead>{t('permitChecks.status')}</TableHead>
              <TableHead>{t('permitChecks.checkedAt')}</TableHead>
              <TableHead>{t('permitChecks.evidence')}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.map((item, index) => (
              <TableRow key={index}>
                <TableCell>{e('doc_type', item.doc_type)}</TableCell>
                <TableCell>{item.number ?? '—'}</TableCell>
                <TableCell>{e('check_source', item.source) || '—'}</TableCell>
                <TableCell>
                  <Chip tone={CHECK_TONE[item.check_status]}>{e('check_status', item.check_status)}</Chip>
                </TableCell>
                <TableCell className="tabular-nums">{date(item.checked_at)}</TableCell>
                <TableCell>
                  <EvidenceList ids={item.evidence_ids} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Panel>
  );
}
