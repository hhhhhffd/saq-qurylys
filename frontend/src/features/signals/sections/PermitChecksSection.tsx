import { useTranslation } from 'react-i18next';
import type { CheckStatus, SignalSections } from '@/api/types';
import { Chip, type ChipTone } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { EvidenceList } from './EvidenceList';
import classes from './Sections.module.css';

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
        <p className={classes.empty}>{t('sections.empty')}</p>
      ) : (
        <div className={classes.scroll}>
          <table className={classes.table}>
            <thead>
              <tr>
                <th>{t('permitChecks.docType')}</th>
                <th>{t('permitChecks.number')}</th>
                <th>{t('permitChecks.source')}</th>
                <th>{t('permitChecks.status')}</th>
                <th>{t('permitChecks.checkedAt')}</th>
                <th>{t('permitChecks.evidence')}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <tr key={index}>
                  <td>{e('doc_type', item.doc_type)}</td>
                  <td>{item.number ?? '—'}</td>
                  <td>{e('check_source', item.source) || '—'}</td>
                  <td>
                    <Chip tone={CHECK_TONE[item.check_status]}>{e('check_status', item.check_status)}</Chip>
                  </td>
                  <td className="tnum">{date(item.checked_at)}</td>
                  <td>
                    <EvidenceList ids={item.evidence_ids} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
