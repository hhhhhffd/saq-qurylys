import { useEffect, useRef } from 'react';
import { Button, Loader, Skeleton } from '@mantine/core';
import { useReducedMotion } from '@mantine/hooks';
import { IconAlertTriangle, IconCheck, IconExternalLink, IconMapPin } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useAd } from '@/api/hooks/ads';
import type { AdRow, AdStatus } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Chip, type ChipTone } from '@/components/Chip';
import { DemoBadge } from '@/components/DemoBadge';
import { EvidenceThumbs } from '@/components/evidence/EvidenceImage';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { HighlightedText } from './HighlightedText';
import { LlmPanel } from './LlmPanel';
import { ObjectLink } from './ObjectLink';
import { PaymentSchemes } from './PaymentSchemes';
import { PhraseHitList } from './PhraseHitList';
import { isHttpUrl } from './url';
import classes from './AdCard.module.css';

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
      className={`panel ${classes.card} ${highlighted ? classes.highlighted : ''}`}
      aria-label={t('card.label', { id: ad.id })}
    >
      <header className={classes.header}>
        <div className={classes.headerMain}>
          {!(view.is_outdoor && view.platform === 'outdoor') && <Chip>{e('platform', view.platform)}</Chip>}
          {view.author && <span className={classes.author}>{view.author}</span>}
          {view.is_outdoor && (
            <Chip title={t('card.outdoorTitle')}>
              <IconMapPin size={12} stroke={2} aria-hidden />
              {t('card.outdoor')}
              {view.lat !== null && view.lon !== null && (
                <span className="tnum">
                  {view.lat.toFixed(5)}, {view.lon.toFixed(5)}
                </span>
              )}
            </Chip>
          )}
        </div>
        <div className={classes.headerMain}>
          {view.is_demo && <DemoBadge />}
          <Chip tone={STATUS_TONE[view.status]}>{e('ad_status', view.status)}</Chip>
        </div>
      </header>

      <div className={classes.meta}>
        <span>
          <span className="faint">{t('card.publishedAt')}</span>{' '}
          <span className="tnum">{f.dateTime(view.published_at)}</span>
        </span>
        <span>
          <span className="faint">{t('card.capturedAt')}</span>{' '}
          <span className="tnum">{f.dateTime(view.captured_at)}</span>
        </span>
        <span>
          <span className="faint">{t('card.weight')}</span>{' '}
          <span className="tnum">
            {t('card.weightValue', { max: view.max_phrase_weight, total: view.total_phrase_weight })}
          </span>
        </span>
      </div>

      {(url !== '' || view.capture_status === 'pending') && (
        <div className={classes.source}>
          {url !== '' &&
            (isHttpUrl(url) ? (
              <a href={url} target="_blank" rel="noopener noreferrer" className={classes.url}>
                <IconExternalLink size={14} stroke={1.8} aria-hidden />
                <span className={classes.urlText}>{url}</span>
              </a>
            ) : (
              <span className={classes.urlText}>{url}</span>
            ))}
          {view.capture_status === 'pending' && (
            <span className={classes.capture} role="status">
              <Loader size="xs" />
              {e('capture_status', 'pending')}
            </span>
          )}
          {view.capture_status === 'done' && (
            <span className={classes.captureDone}>
              <IconCheck size={13} stroke={2} aria-hidden />
              {e('capture_status', 'done')}
            </span>
          )}
        </div>
      )}
      {view.capture_status === 'failed' && (
        <div className={classes.captureFailed} role="alert">
          <IconAlertTriangle size={14} stroke={1.8} aria-hidden />
          <span>
            <strong>{e('capture_status', 'failed')}</strong>
            {view.capture_error ? `: ${view.capture_error}` : ''}
          </span>
        </div>
      )}

      <div className={classes.section}>
        {view.text ? (
          <HighlightedText text={view.text} hits={detail?.phrase_hits ?? []} focusHitId={focusHitId} />
        ) : (
          <p className="faint">{t('card.noText')}</p>
        )}
        {(view.ocr_status === 'pending' || view.ocr_status === 'failed') && (
          <div className={classes.chips}>
            {view.ocr_status === 'pending' ? (
              <span className={classes.capture} role="status">
                <Loader size="xs" />
                {e('ocr_status', 'pending')}
              </span>
            ) : (
              <Chip tone="yellow">
                <IconAlertTriangle size={12} stroke={2} aria-hidden />
                {e('ocr_status', 'failed')}
              </Chip>
            )}
          </div>
        )}
        {detailQuery.isPending && <Skeleton h={14} w="55%" />}
        {detailQuery.isError && (
          <div className={classes.detailError} role="alert">
            <span>{t('card.detailsError')}</span>
            <Button size="compact-xs" variant="default" onClick={() => void detailQuery.refetch()}>
              {t('retry', { ns: 'common' })}
            </Button>
          </div>
        )}
        {detail && detail.phrase_hits.length > 0 && (
          <PhraseHitList adId={ad.id} hits={detail.phrase_hits} editable={canEditRegistry} focusHitId={focusHitId} />
        )}
      </div>

      <div className={`${classes.section} ${classes.facts}`}>
        {view.phones.length > 0 && (
          <div className={classes.fact}>
            <span className={classes.label}>{t('card.phones')}</span>
            <div className={classes.chips}>
              {view.phones.map((phone) => (
                <Chip key={phone}>
                  <span className="tnum">{phone}</span>
                </Chip>
              ))}
            </div>
          </div>
        )}
        <PaymentSchemes ad={view} editable={canEditRegistry} />
        {(view.claimed_readiness_pct !== null || view.price_before_completion) && (
          <div className={classes.fact}>
            <span className={classes.label}>{t('card.claims')}</span>
            <div className={classes.chips}>
              {view.claimed_readiness_pct !== null && (
                <span>
                  {t('card.readiness')}:{' '}
                  <span className="tnum">
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

      {detail && detail.evidence.length > 0 && (
        <div className={classes.section}>
          <span className={classes.label}>{t('card.evidence')}</span>
          <EvidenceThumbs evidence={detail.evidence} size={88} />
        </div>
      )}
    </article>
  );
}
