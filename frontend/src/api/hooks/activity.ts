import { useEffect, useEffectEvent, useRef } from 'react';
import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { api } from '../client';
import { qk } from '../keys';
import { invalidateObjectData } from './objects';
import type { ActivityEvent, ActivityFeed } from '../types';

const POLL_MS = 4000;
/**
 * Ids of the latest events the client has taken. A poll repeats the events of the last 2 minutes before the cursor
 * (up to 50 of each of the 4 kinds), so the memory must hold more than that.
 */
const SEEN_LIMIT = 400;

/** What one poll returned. `cursor` is where the next one starts; it lives in the query cache. */
interface ActivityBatch {
  cursor: string;
  /** events not seen before, newest first; none on the first poll and after a reset */
  events: ActivityEvent[];
  /** the cursor was too old: the page is refreshed instead of the missed events being played */
  reset: boolean;
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

/** After a long absence nobody knows what changed: everything on screen is refetched, except the feed itself. */
function invalidateAll(qc: QueryClient) {
  void qc.invalidateQueries({ predicate: (query) => query.queryKey[0] !== qk.activity[0] });
}

/**
 * Polls the live feed every 4 s while the tab is visible (TanStack pauses interval refetches in the background).
 * The first poll only takes the cursor: events that happened before the page opened are not replayed. Neither are
 * the events missed while the tab was hidden for long: the server answers such a poll with `reset`, and the page
 * is refreshed without animation.
 * Calls `onEvents` with the new events, oldest first, once per batch.
 */
export function useActivityFeed(onEvents: (events: ActivityEvent[]) => void) {
  const qc = useQueryClient();
  // Insertion order is the order of arrival, so the oldest id is the first to go.
  const seen = useRef(new Set<string>());
  // When the newest event the client was told about at the start (or after a reset) happened: the 2 minutes the
  // server looks back from the cursor reach older events that were there already and are not news.
  const startedAt = useRef(0);
  const query = useQuery({
    queryKey: qk.activity,
    queryFn: async () => {
      const previous = qc.getQueryData<ActivityBatch>(qk.activity);
      const feed = await api<ActivityFeed>('/activity', { params: { after: previous?.cursor } });
      const starting = !previous || feed.reset;
      if (starting) {
        seen.current.clear();
        startedAt.current = feed.items.length > 0 ? Date.parse(feed.items[0].at) : 0;
      }
      const fresh = feed.items.filter(
        (event) => !seen.current.has(event.id) && Date.parse(event.at) >= startedAt.current,
      );
      for (const event of [...feed.items].reverse()) seen.current.add(event.id);
      for (const id of seen.current) {
        if (seen.current.size <= SEEN_LIMIT) break;
        seen.current.delete(id);
      }
      return { cursor: feed.cursor, events: starting ? [] : fresh, reset: feed.reset } satisfies ActivityBatch;
    },
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
    staleTime: 0,
  });

  const handle = useEffectEvent((batch: ActivityBatch) => {
    if (batch.reset) {
      invalidateAll(qc);
      return;
    }
    invalidateAffected(qc, batch.events);
    onEvents([...batch.events].reverse());
  });
  const batch = query.data;
  useEffect(() => {
    if (batch && (batch.reset || batch.events.length > 0)) handle(batch);
  }, [batch]);

  return query;
}
