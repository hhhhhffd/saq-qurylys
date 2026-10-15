import { useTranslation } from 'react-i18next';
import type { EvidenceRef, NeedsCheck } from '@/api/types';
import { Chip } from '@/components/Chip';
import { useEnum } from '@/i18n/useEnum';
import { EvidenceRefLink } from './EvidenceRefLink';
import classes from './NeedsCheckList.module.css';

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
    <section className={classes.root} aria-labelledby="needs-check-title">
      <div className={classes.head}>
        <h4 id="needs-check-title" className={classes.title}>
          {t('card.needsCheck.title')}
        </h4>
        <Chip tone="yellow">{t('card.needsCheck.zeroPoints')}</Chip>
      </div>
      <p className={classes.note}>{t('card.needsCheck.note')}</p>
      <ul className={classes.list}>
        {items.map((item) => {
          const refs = refsOf(item);
          return (
            <li key={item.code} className={classes.item}>
              <strong>{e('needs_check', item.code)}</strong>
              <p className={classes.desc}>{e('needs_check_desc', item.code, { ...item.detail })}</p>
              {refs.length > 0 && (
                <div className={classes.refs}>
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
