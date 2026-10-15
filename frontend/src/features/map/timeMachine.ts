import { useEffect, useState } from 'react';
import { useReducedMotion } from '@/lib/hooks';
import type { DashboardCounts, ObjectRow, TimelineFrame } from '@/api/types';

export const SPEEDS = [1, 2, 4] as const;
export type Speed = (typeof SPEEDS)[number];

/** How long a frame stays on screen at ×1. */
const FRAME_MS = 1000;

/**
 * The dashboard rows as they were at a frame: the zone and score of that moment. An object that had no score yet
 * has none here either. The key status was not recorded, so it is left out. Most dangerous first, like the dashboard.
 */
export function rowsAtFrame(rows: ObjectRow[], frame: TimelineFrame): ObjectRow[] {
  const scored = new Map(frame.objects.map((item) => [item.object_id, item]));
  return rows
    .map((row) => ({
      ...row,
      zone: scored.get(row.id)?.zone ?? null,
      score: scored.get(row.id)?.score ?? null,
      key_status: null,
      key_status_detail: null,
    }))
    .sort((a, b) => (b.score ?? -1) - (a.score ?? -1) || a.id - b.id);
}

export function countZones(rows: ObjectRow[]): DashboardCounts {
  const counts: DashboardCounts = { green: 0, yellow: 0, red: 0, unscored: 0, total: rows.length };
  for (const row of rows) counts[row.zone ?? 'unscored'] += 1;
  return counts;
}

/**
 * State of the time machine: which of `frameCount` frames is shown (the last one is today) and the playback.
 * Leaving the mode (`enabled` false) forgets all of it. Moving the slider pauses; a finished playback stops
 * at today, and starting it again there goes back to the first frame. With reduced motion the speed stays ×1.
 */
export function useTimeMachine(frameCount: number, enabled: boolean) {
  const reducedMotion = useReducedMotion();
  const last = Math.max(frameCount - 1, 0);
  const [wasEnabled, setWasEnabled] = useState(enabled);
  const [requested, setRequested] = useState<number | null>(null);
  const [wantsPlay, setWantsPlay] = useState(false);
  const [chosenSpeed, setSpeed] = useState<Speed>(1);

  if (wasEnabled !== enabled) {
    setWasEnabled(enabled);
    setRequested(null);
    setWantsPlay(false);
  }

  const speed = reducedMotion ? 1 : chosenSpeed;
  const index = Math.min(requested ?? last, last);
  const playing = wantsPlay && index < last;

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(
      () => setRequested((current) => Math.min((current ?? last) + 1, last)),
      FRAME_MS / speed,
    );
    return () => window.clearInterval(timer);
  }, [playing, speed, last]);

  return {
    index,
    last,
    /** the frame is today: the map shows live data */
    isToday: index === last,
    playing,
    speed,
    speedLocked: reducedMotion,
    seek: (next: number) => {
      setWantsPlay(false);
      setRequested(next >= last ? null : next);
    },
    togglePlay: () => {
      if (playing) {
        setWantsPlay(false);
        return;
      }
      if (index >= last) setRequested(0);
      setWantsPlay(true);
    },
    setSpeed,
  };
}
