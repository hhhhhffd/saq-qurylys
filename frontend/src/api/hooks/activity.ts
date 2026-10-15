import { useEffect, useEffectEvent } from 'react';
import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { api } from '../client';
import { qk } from '../keys';
import { invalidateObjectData } from './objects';
import type { ActivityEvent, ActivityFeed } from '../types';

const POLL_MS = 4000;

/** What one poll returned. `cursor` is where the next one starts; it lives in the query cache. */
interface ActivityBatch {
  cursor: string;
  /** events that happened since the previous poll, newest first */
  events: ActivityEvent[];
}

/** Refreshes the data the events are about, so the page behind the island changes live. */
function invalidateAffected(qc: QueryClient, events: ActivityEvent[]) {
  const kinds = new Set(events.map((event) => event.kind));
  if (kinds.has('score_changed')) invalidateObjectData(qc);
  if (kinds.has('ad_received')) {
    void qc.invalidateQueries({ queryKey: qk.ads });
    for (const event of events) {
      if (event.kind === 'ad_received' && event.object_id !== null) {
        void qc.invalidateQueries({ queryKey: qk.object(event.object_id) });
      }
    }
  }
  if (kinds.has('signal_created') || kinds.has('signal_sent')) {
    void qc.invalidateQueries({ queryKey: qk.signals });
    void qc.invalidateQueries({ queryKey: qk.notifications });
  }
}

/**
 * Polls the live feed every 4 s while the tab is visible (TanStack pauses interval refetches in the background).
 * The first poll only takes the cursor: events that happened before the page opened are not replayed.
 * Calls `onEvents` with the new events, oldest first, once per batch.
 */
export function useActivityFeed(onEvents: (events: ActivityEvent[]) => void) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: qk.activity,
    queryFn: async () => {
      const previous = qc.getQueryData<ActivityBatch>(qk.activity);
      const feed = await api<ActivityFeed>('/activity', { params: { after: previous?.cursor } });
      return { cursor: feed.cursor, events: previous ? feed.items : [] } satisfies ActivityBatch;
    },
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
    staleTime: 0,
  });

  const handle = useEffectEvent((events: ActivityEvent[]) => {
    invalidateAffected(qc, events);
    onEvents([...events].reverse());
  });
  const events = query.data?.events;
  useEffect(() => {
    if (events && events.length > 0) handle(events);
  }, [events]);

  return query;
}
