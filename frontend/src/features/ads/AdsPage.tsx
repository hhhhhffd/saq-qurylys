import { useRef, useState } from 'react';
import { IconCamera, IconPlus, IconRss } from '@tabler/icons-react';
import { Link, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useAd, useAds } from '@/api/hooks/ads';
import { useAuth } from '@/auth/useAuth';
import { PageHeader } from '@/components/PageHeader';
import { EmptyState, ErrorBlock } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { AdCard } from './AdCard';
import { AdFilters, type AdFilterValues } from './AdFilters';
import { AdsPager } from './AdsPager';
import { CaptureModal } from './CaptureModal';
import { ManualAdModal } from './ManualAdModal';
import { PAGE_SIZE, parseAdStatus, parseDemo, parseId, parsePlatform } from './constants';

function FeedSkeleton({ count = 3 }: { count?: number }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col gap-3" role="status" aria-label={t('loading')}>
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="flex flex-col gap-2.5 rounded border border-border bg-surface p-4">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3 w-1/2" />
          <Skeleton className="h-3.5 w-full" />
          <Skeleton className="h-3.5 w-5/6" />
          <Skeleton className="h-3.5 w-3/5" />
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
              <Button className="max-sm:min-h-11" onClick={() => setCaptureOpen(true)}>
                <IconCamera />
                {t('actions.capture')}
              </Button>
              <Button className="max-sm:min-h-11" variant="secondary" onClick={() => setManualOpen(true)}>
                <IconPlus />
                {t('actions.manual')}
              </Button>
              <Button variant="secondary" asChild>
                <Link to="/sources">
                  <IconRss />
                  {t('actions.sources')}
                </Link>
              </Button>
            </>
          )
        }
      />
      <p className="mb-4 max-w-4xl text-sm leading-5 text-text-2">{t('feed.workflowHint')}</p>
      <AdFilters
        values={filters}
        onChange={changeFilters}
        onReset={() => setParams(new URLSearchParams())}
        canReset={canReset}
      />

      {showPinned && (
        <section className="mb-5" aria-label={t('feed.pinned')}>
          <div className="mb-2 flex items-center justify-between gap-3 text-sm">
            <span className="text-2xs font-bold tracking-wider text-text-3 uppercase">{t('feed.pinned')}</span>
            <Button variant="ghost" size="xs" onClick={() => updateParams({ ad: null, hit: null })}>
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
        className={cn('flex flex-col gap-3.5 transition-opacity duration-(--dur)', ads.isPlaceholderData && 'opacity-60')}
        aria-busy={ads.isFetching}
      >
        {ads.isPending && <FeedSkeleton />}
        {ads.isError && <ErrorBlock error={ads.error} onRetry={() => void ads.refetch()} />}
        {ads.data && items.length === 0 && (
          <EmptyState
            action={
              total > 0 ? (
                <Button variant="secondary" size="xs" onClick={() => changePage(1)}>
                  {t('feed.firstPage')}
                </Button>
              ) : canReset ? (
                <Button variant="secondary" size="xs" onClick={() => setParams(new URLSearchParams())}>
                  {t('reset', { ns: 'common' })}
                </Button>
              ) : canEditRegistry ? (
                <div className="flex flex-wrap gap-2">
                  <Button size="sm" className="max-sm:min-h-11" onClick={() => setCaptureOpen(true)}>
                    {t('actions.capture')}
                  </Button>
                  <Button className="max-sm:min-h-11" variant="secondary" size="sm" onClick={() => setManualOpen(true)}>
                    {t('actions.manual')}
                  </Button>
                </div>
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
          <CaptureModal open={captureOpen} onClose={() => setCaptureOpen(false)} onCreated={showAd} />
          <ManualAdModal open={manualOpen} onClose={() => setManualOpen(false)} onCreated={showAd} />
        </>
      )}
    </>
  );
}
