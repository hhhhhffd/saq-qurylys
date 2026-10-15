import { useTranslation } from 'react-i18next';
import type { EvidenceRef, NeedsCheck } from '@/api/types';
import { Chip } from '@/components/Chip';
import { useEnum } from '@/i18n/useEnum';
import { EvidenceRefLink } from './EvidenceRefLink';

function refsOf(item: NeedsCheck): EvidenceRef[] {
  switch (item.code) {
    case 'complaint_unverified':
      return item.detail.complaint_ids.map((id) => ({ type: 'complaint', id }));
    case 'ai_hypotheses_pending':
    case 'link_unverified':
      return item.detail.ad_post_ids.map((id) => ({ type: 'ad_post', id }));
    default:
      return [];
  }
}

interface Props {
  items: NeedsCheck[];
  linked?: boolean;
  anchors?: boolean;
}

/** Unknown or unconfirmed facts: they add 0 points and are shown apart from the factors (D17). */
export function NeedsCheckList({ items, linked, anchors }: Props) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  if (items.length === 0) return null;

  return (
    <section className="mt-4 rounded border border-zone-yellow/30 bg-zone-yellow-bg px-3 py-2.5" aria-labelledby="needs-check-title">
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <h4 id="needs-check-title" className="m-0 font-heading text-2xs font-bold tracking-wider text-zone-yellow-ink uppercase">
          {t('card.needsCheck.title')}
        </h4>
        <Chip tone="yellow">{t('card.needsCheck.zeroPoints')}</Chip>
      </div>
      <p className="mt-1 text-xs text-text-2">{t('card.needsCheck.note')}</p>
      <ul className="mt-2.5 flex list-none flex-col gap-2.5 p-0">
        {items.map((item) => {
          const refs = refsOf(item);
          return (
            <li key={item.code} className="text-sm">
              <strong className="font-semibold text-text">{e('needs_check', item.code)}</strong>
              <p className="mt-0.5 text-text-2">{e('needs_check_desc', item.code, { ...item.detail })}</p>
              {refs.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-x-1.5 gap-y-1">
                  {refs.map((ref) => (
                    <EvidenceRefLink
                      key={`${ref.type}-${ref.id}`}
                      evidenceRef={ref}
                      linked={linked}
                      anchors={anchors}
                    />
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
