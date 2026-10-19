import { useTranslation } from 'react-i18next';
import { useSettings } from '@/api/hooks/reference';
import { findFactor, readBreakdown, type ObjectDetail } from '@/api/types';
import { useEnum } from '@/i18n/useEnum';

/** A plain-language digest of what the registry holds about the object. Facts only, no verdict. */
export function KnownFacts({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const settings = useSettings().data;
  const breakdown = readBreakdown(object.latest_score);
  const windowDays = settings?.ad_window_days ?? findFactor(breakdown, 'r3_active_ads')?.detail.window_days;
  const lower = (text: string) => text.toLocaleLowerCase();

  const ads = t('card.risk.publications', { count: object.ads_7d_count });
  const sentences = [
    t('card.known.status', { status: lower(e('construction_status', object.construction_status)) }),
    object.readiness_actual_pct !== null && object.readiness_claimed_pct !== null
      ? t('card.known.readiness', { actual: object.readiness_actual_pct, claimed: object.readiness_claimed_pct })
      : null,
    breakdown ? t('card.known.legal', { status: lower(e('legal_basis_status', breakdown.legal_basis_status)) }) : null,
    windowDays === undefined ? t('card.known.adsNoPeriod', { ads }) : t('card.known.ads', { days: windowDays, ads }),
    t('card.known.complaints', { count: object.complaints.length }),
    object.developer ? t('card.known.developer', { name: object.developer.name }) : t('card.known.developerNone'),
  ].filter((sentence): sentence is string => sentence !== null);

  return (
    <section aria-labelledby="known-facts-title" data-testid="known-facts">
      <h3 id="known-facts-title" className="font-heading text-2xs font-bold tracking-wider text-text uppercase">
        {t('card.known.title')}
      </h3>
      <p className="mt-1.5 text-base leading-relaxed text-text-2">{sentences.join(' ')}</p>
      <p className="mt-1 text-xs text-text-3">{t('card.known.note')}</p>
    </section>
  );
}
