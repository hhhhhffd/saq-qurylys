import { useEffect, useRef } from 'react';
import { useReducedMotion } from '@/lib/hooks';
import { IconAlertTriangle, IconCheck, IconExternalLink, IconMapPin } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useAd } from '@/api/hooks/ads';
import type { AdRow, AdStatus } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Chip, type ChipTone } from '@/components/Chip';
import { DemoBadge } from '@/components/DemoBadge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Spinner } from '@/components/ui/spinner';
import { EvidenceThumbs } from '@/components/evidence/EvidenceImage';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { cn } from '@/lib/utils';
import { AdVersionsPanel } from './AdVersionsPanel';
import { HighlightedText } from './HighlightedText';
import { LlmPanel } from './LlmPanel';
import { ObjectLink } from './ObjectLink';
import { PaymentSchemes } from './PaymentSchemes';
import { PhraseHitList } from './PhraseHitList';
import { isHttpUrl } from './url';

const sectionClass = 'flex flex-col gap-2.5 border-t border-border pt-3';
const factClass = 'flex min-w-0 flex-col gap-1 text-sm';
const labelClass = 'text-xs font-medium text-text-3';
const chipsClass = 'flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1.5';

const STATUS_TONE: Record<AdStatus, ChipTone> = {
  captured: 'green',
  verification: 'yellow',
  removed_saved: 'neutral',
};

interface Props {
  ad: AdRow;
  /** the publication opened through `?ad=`: scrolled into view and ringed */
  highlighted?: boolean;
  /** the phrase hit the risk-factor evidence points to (`?hit=`) */
  focusHitId?: number | null;
}

export function AdCard({ ad, highlighted = false, focusHitId = null }: Props) {
  const { t } = useTranslation('ads');
  const e = useEnum();
  const f = useFormat();
  const { canEditRegistry } = useAuth();
  const detailQuery = useAd(ad.id);
  const detail = detailQuery.data;
  // Show what the list row already has until the detail arrives.
  const view: AdRow = detail ?? ad;
  const ref = useRef<HTMLElement>(null);
  const reducedMotion = useReducedMotion();
  const detailLoaded = detail !== undefined;

  // Scroll again once the detail is in: the card grows when hits and evidence appear.
  useEffect(() => {
    if (highlighted) {
      ref.current?.scrollIntoView({ block: 'center', behavior: reducedMotion ? 'auto' : 'smooth' });
    }
  }, [highlighted, detailLoaded, reducedMotion]);

  const url = view.url ?? '';

  return (
    <article
      ref={ref}
      id={`ad-${ad.id}`}
      className={cn(
        'flex min-w-0 scroll-mt-[calc(var(--header-h)+16px)] flex-col gap-3 rounded border border-border bg-surface p-4 transition-shadow duration-(--dur)',
        highlighted && 'shadow-2 ring-2 ring-focus',
      )}
      aria-label={t('card.label', { id: ad.id })}
    >
      <header className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1.5">
          {!(view.is_outdoor && view.platform === 'outdoor') && <Chip>{e('platform', view.platform)}</Chip>}
          {view.author && <span className="font-heading text-sm font-semibold [overflow-wrap:anywhere]">{view.author}</span>}
          {view.is_outdoor && (
            <Chip title={t('card.outdoorTitle')}>
              <IconMapPin aria-hidden />
              {t('card.outdoor')}
              {view.lat !== null && view.lon !== null && (
                <span className="tabular-nums">
                  {view.lat.toFixed(5)}, {view.lon.toFixed(5)}
                </span>
              )}
            </Chip>
          )}
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1.5">
          {view.is_demo && <DemoBadge />}
          <Chip tone={STATUS_TONE[view.status]}>{e('ad_status', view.status)}</Chip>
          {/* A removed post whose link is still unconfirmed stays `verification`: the removal is its own fact. */}
          {view.removed_detected_at !== null && view.status !== 'removed_saved' && (
            <Chip tone={STATUS_TONE.removed_saved}>{e('ad_status', 'removed_saved')}</Chip>
          )}
        </div>
      </header>

      <div className="flex flex-wrap gap-x-4.5 gap-y-0.5 text-sm text-text-2">
        <span>
          <span className="text-text-3">{t('card.publishedAt')}</span>{' '}
          <span className="tabular-nums">{f.dateTime(view.published_at)}</span>
        </span>
        <span>
          <span className="text-text-3">{t('card.capturedAt')}</span>{' '}
          <span className="tabular-nums">{f.dateTime(view.captured_at)}</span>
        </span>
        <span>
          <span className="text-text-3">{t('card.weight')}</span>{' '}
          <span className="tabular-nums">
            {t('card.weightValue', { max: view.max_phrase_weight, total: view.total_phrase_weight })}
          </span>
        </span>
      </div>

      {(url !== '' || view.capture_status === 'pending') && (
        <div className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          {url !== '' &&
            (isHttpUrl(url) ? (
              <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex max-w-full min-w-0 items-center gap-1 text-link hover:underline"
              >
                <IconExternalLink className="size-3.5 shrink-0" aria-hidden />
                <span className="min-w-0 truncate">{url}</span>
              </a>
            ) : (
              <span className="min-w-0 truncate">{url}</span>
            ))}
          {view.capture_status === 'pending' && (
            <span className="inline-flex items-center gap-1.5 text-sm text-text-2" role="status">
              <Spinner className="size-3.5" />
              {e('capture_status', 'pending')}
            </span>
          )}
          {view.capture_status === 'done' && (
            <span className="inline-flex items-center gap-1.5 text-sm text-text-3">
              <IconCheck className="size-3.5" aria-hidden />
              {e('capture_status', 'done')}
            </span>
          )}
        </div>
      )}
      {view.capture_status === 'failed' && (
        <div
          className="flex items-start gap-2 rounded border border-zone-red/40 bg-zone-red-bg px-2.5 py-2 text-sm text-zone-red-ink [overflow-wrap:anywhere]"
          role="alert"
        >
          <IconAlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span>
            <strong>{e('capture_status', 'failed')}</strong>
            {view.capture_error ? `: ${view.capture_error}` : ''}
          </span>
        </div>
      )}

      <div className={sectionClass}>
        {view.text ? (
          <HighlightedText text={view.text} hits={detail?.phrase_hits ?? []} focusHitId={focusHitId} />
        ) : (
          <p className="text-text-3">{t('card.noText')}</p>
        )}
        {(view.ocr_status === 'pending' || view.ocr_status === 'failed') && (
          <div className={chipsClass}>
            {view.ocr_status === 'pending' ? (
              <span className="inline-flex items-center gap-1.5 text-sm text-text-2" role="status">
                <Spinner className="size-3.5" />
                {e('ocr_status', 'pending')}
              </span>
            ) : (
              <Chip tone="yellow">
                <IconAlertTriangle aria-hidden />
                {e('ocr_status', 'failed')}
              </Chip>
            )}
          </div>
        )}
        {detailQuery.isPending && <Skeleton className="h-3.5 w-1/2" />}
        {detailQuery.isError && (
          <div className="flex flex-wrap items-center gap-2 text-sm text-text-2" role="alert">
            <span>{t('card.detailsError')}</span>
            <Button size="xs" variant="secondary" onClick={() => void detailQuery.refetch()}>
              {t('retry', { ns: 'common' })}
            </Button>
          </div>
        )}
        {detail && detail.phrase_hits.length > 0 && (
          <PhraseHitList adId={ad.id} hits={detail.phrase_hits} editable={canEditRegistry} focusHitId={focusHitId} />
        )}
      </div>

      <div className={sectionClass}>
        {view.phones.length > 0 && (
          <div className={factClass}>
            <span className={labelClass}>{t('card.phones')}</span>
            <div className={chipsClass}>
              {view.phones.map((phone) => (
                <Chip key={phone}>
                  <span className="tabular-nums">{phone}</span>
                </Chip>
              ))}
            </div>
          </div>
        )}
        <PaymentSchemes ad={view} editable={canEditRegistry} />
        {(view.claimed_readiness_pct !== null || view.price_before_completion) && (
          <div className={factClass}>
            <span className={labelClass}>{t('card.claims')}</span>
            <div className={chipsClass}>
              {view.claimed_readiness_pct !== null && (
                <span>
                  {t('card.readiness')}:{' '}
                  <span className="tabular-nums">
                    {view.claimed_readiness_pct}
                    {t('units.pct', { ns: 'common' })}
                  </span>
                </span>
              )}
              {view.price_before_completion && <Chip tone="yellow">{t('card.priceBeforeCompletion')}</Chip>}
            </div>
          </div>
        )}
        <ObjectLink ad={view} linked={detail?.linked_object ?? null} editable={canEditRegistry} />
      </div>

      <LlmPanel ad={view} extraction={detail?.llm_extraction ?? null} editable={canEditRegistry} />

      {detail && <AdVersionsPanel ad={detail} />}

      {detail && detail.evidence.length > 0 && (
        <div className={sectionClass}>
          <span className={labelClass}>{t('card.evidence')}</span>
          <EvidenceThumbs evidence={detail.evidence} size={88} />
        </div>
      )}
    </article>
  );
}
