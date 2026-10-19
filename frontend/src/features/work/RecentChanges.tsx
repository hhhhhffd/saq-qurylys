import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { api } from '@/api/client';
import type { ActivityEvent, ActivityFeed } from '@/api/types';
import { EmptyState, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';

/** Not `qk.activity`: that query holds the header island's polling cursor, this one is a plain snapshot. */
function useRecentEvents() {
  return useQuery({
    queryKey: ['work', 'recent-activity'],
    queryFn: () => api<ActivityFeed>('/activity'),
    staleTime: 60_000,
  });
}

function useEventLine() {
  const { t } = useTranslation('activity');
  const e = useEnum();
  return (event: ActivityEvent): { text: string; to: string } => {
    const join = (...parts: (string | null)[]) => parts.filter(Boolean).join(' · ');
    switch (event.kind) {
      case 'ad_received':
        return {
          text: join(event.origin === 'citizen' ? t('title.adCitizen') : t('title.adStaff'), event.object_name),
          to: `/ads?ad=${event.ad_id}`,
        };
      case 'signal_created':
        return { text: join(t('title.signalCreated'), event.number, event.object_name), to: `/signals/${event.signal_id}` };
      case 'signal_sent':
        return { text: join(t('title.signalSent'), event.number, event.object_name), to: `/signals/${event.signal_id}` };
      case 'score_changed':
        return {
          text: join(
            event.object_name,
            event.zone_before !== event.zone_after
              ? t('score.zone', { from: e('zone', event.zone_before), to: e('zone', event.zone_after) })
              : (event.score_after ?? 0) > (event.score_before ?? 0)
                ? t('score.up')
                : t('score.down'),
          ),
          to: `/objects/${event.object_id}`,
        };
    }
  };
}

/** The latest events in the user's territory (the API gives the newest few of the last 7 days). */
export function RecentChanges() {
  const { t } = useTranslation();
  const { dateTime } = useFormat();
  const query = useRecentEvents();
  const line = useEventLine();

  return (
    <section className="space-y-2" aria-labelledby="work-recent-title">
      <h2 id="work-recent-title" className="text-lg font-semibold">
        {t('work.recentTitle')}
      </h2>
      <div className="rounded border border-border bg-surface px-3">
        {query.isPending ? (
          <LoadingBlock label={t('work.loadingRecent')} />
        ) : query.isError ? (
          <ErrorBlock error={query.error} onRetry={() => void query.refetch()} />
        ) : query.data.items.length === 0 ? (
          <EmptyState>{t('work.recentEmpty')}</EmptyState>
        ) : (
          <ul className="m-0 list-none divide-y divide-border p-0">
            {query.data.items.slice(0, 8).map((event) => {
              const { text, to } = line(event);
              return (
                <li key={event.id} className="flex gap-3 py-2">
                  <span className="mt-1.5 size-2 flex-none rounded-full bg-border-strong" aria-hidden />
                  <div className="min-w-0 text-sm">
                    <time className="block text-xs tabular-nums text-text-3" dateTime={event.at}>
                      {dateTime(event.at)}
                    </time>
                    <Link to={to} className="[overflow-wrap:anywhere]">
                      {text}
                    </Link>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
