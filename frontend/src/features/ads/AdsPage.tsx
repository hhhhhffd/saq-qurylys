import { useRef, useState } from 'react';
import { Button, Skeleton } from '@mantine/core';
import { IconCamera, IconPlus } from '@tabler/icons-react';
import { useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useAd, useAds } from '@/api/hooks/ads';
import { useAuth } from '@/auth/useAuth';
import { PageHeader } from '@/components/PageHeader';
import { EmptyState, ErrorBlock } from '@/components/QueryState';
import { AdCard } from './AdCard';
import { AdFilters, type AdFilterValues } from './AdFilters';
import { AdsPager } from './AdsPager';
import { CaptureModal } from './CaptureModal';
import { ManualAdModal } from './ManualAdModal';
import { PAGE_SIZE, parseAdStatus, parseDemo, parseId, parsePlatform } from './constants';
import classes from './AdsPage.module.css';

function FeedSkeleton({ count = 3 }: { count?: number }) {
  const { t } = useTranslation();
  return (
    <div className={classes.feed} role="status" aria-label={t('loading')}>
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className={`panel ${classes.skeleton}`}>
          <Skeleton h={18} w="35%" />
          <Skeleton h={12} w="50%" />
          <Skeleton h={14} />
          <Skeleton h={14} w="85%" />
          <Skeleton h={14} w="60%" />
        </div>
      ))}
    </div>
  );
}

export function AdsPage() {
  const { t } = useTranslation('ads');
  const { canEditRegistry } = useAuth();
  const [params, setParams] = useSearchParams();
  const [captureOpen, setCaptureOpen] = useState(false);
  const [manualOpen, setManualOpen] = useState(false);
  const feedRef = useRef<HTMLDivElement>(null);

  const filters: AdFilterValues = {
    platform: parsePlatform(params.get('platform')),
    objectId: parseId(params.get('object_id')),
    status: parseAdStatus(params.get('status')),
    demo: parseDemo(params.get('is_demo')),
    q: params.get('q') ?? '',
  };
  const page = parseId(params.get('page')) ?? 1;
  const adId = parseId(params.get('ad'));
  const focusHitId = parseId(params.get('hit'));

  const ads = useAds({
    platform: filters.platform ?? undefined,
    object_id: filters.objectId ?? undefined,
    status: filters.status ?? undefined,
    is_demo: filters.demo ?? undefined,
    q: filters.q.trim() || undefined,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  // Shares its cache entry with the card of the same publication.
  const pinnedAd = useAd(adId);

  const items = ads.data?.items ?? [];
  const total = ads.data?.total ?? 0;
  // The opened publication is pinned above the feed (and left out of it): cards above it in the feed grow as
  // their details load, which would push it out of view after the scroll.
  const showPinned = adId !== null;
  const canReset = params.size > 0;

  const updateParams = (patch: Record<string, string | null>) =>
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      for (const [key, value] of Object.entries(patch)) {
        if (value) next.set(key, value);
        else next.delete(key);
      }
      return next;
    });

  const changeFilters = (patch: Partial<AdFilterValues>) => {
    const next: Record<string, string | null> = { page: null };
    if (patch.platform !== undefined) next.platform = patch.platform;
    if (patch.status !== undefined) next.status = patch.status;
    if (patch.demo !== undefined) next.is_demo = patch.demo === null ? null : String(patch.demo);
    if (patch.q !== undefined) next.q = patch.q;
    if (patch.objectId !== undefined) next.object_id = patch.objectId === null ? null : String(patch.objectId);
    updateParams(next);
  };

  const changePage = (nextPage: number) => {
    updateParams({ page: nextPage > 1 ? String(nextPage) : null });
    feedRef.current?.scrollIntoView({ block: 'start' });
  };

  const showAd = (id: number) => updateParams({ ad: String(id), hit: null });

  return (
    <>
      <PageHeader
        title={t('title')}
        subtitle={t('subtitle')}
        actions={
          canEditRegistry && (
            <>
              <Button leftSection={<IconCamera size={16} stroke={1.8} />} onClick={() => setCaptureOpen(true)}>
                {t('actions.capture')}
              </Button>
              <Button
                variant="default"
                leftSection={<IconPlus size={16} stroke={1.8} />}
                onClick={() => setManualOpen(true)}
              >
                {t('actions.manual')}
              </Button>
            </>
          )
        }
      />
      <AdFilters
        values={filters}
        onChange={changeFilters}
        onReset={() => setParams(new URLSearchParams())}
        canReset={canReset}
      />

      {showPinned && (
        <section className={classes.pinned} aria-label={t('feed.pinned')}>
          <div className={classes.pinnedHead}>
            <span className="muted">{t('feed.pinned')}</span>
            <Button variant="subtle" size="compact-xs" onClick={() => updateParams({ ad: null, hit: null })}>
              {t('feed.unpin')}
            </Button>
          </div>
          {pinnedAd.isPending && <FeedSkeleton count={1} />}
          {pinnedAd.isError && <ErrorBlock error={pinnedAd.error} onRetry={() => void pinnedAd.refetch()} />}
          {pinnedAd.data && <AdCard ad={pinnedAd.data} highlighted focusHitId={focusHitId} />}
        </section>
      )}

      <div
        ref={feedRef}
        className={`${classes.feed} ${ads.isPlaceholderData ? classes.stale : ''}`}
        aria-busy={ads.isFetching}
      >
        {ads.isPending && <FeedSkeleton />}
        {ads.isError && <ErrorBlock error={ads.error} onRetry={() => void ads.refetch()} />}
        {ads.data && items.length === 0 && (
          <EmptyState
            action={
              total > 0 ? (
                <Button variant="default" size="xs" onClick={() => changePage(1)}>
                  {t('feed.firstPage')}
                </Button>
              ) : canEditRegistry ? (
                <Button variant="default" size="xs" onClick={() => setCaptureOpen(true)}>
                  {t('actions.capture')}
                </Button>
              ) : undefined
            }
          >
            <strong>{total > 0 ? t('feed.pageEmpty') : t('feed.empty')}</strong>
            {total === 0 && (
              <>
                <br />
                {t('feed.emptyHint')}
              </>
            )}
          </EmptyState>
        )}
        {items
          .filter((ad) => ad.id !== adId)
          .map((ad) => (
            <AdCard key={ad.id} ad={ad} />
          ))}
      </div>

      {items.length > 0 && <AdsPager page={page} total={total} onPageChange={changePage} />}

      {canEditRegistry && (
        <>
          <CaptureModal opened={captureOpen} onClose={() => setCaptureOpen(false)} onCreated={showAd} />
          <ManualAdModal opened={manualOpen} onClose={() => setManualOpen(false)} onCreated={showAd} />
        </>
      )}
    </>
  );
}
