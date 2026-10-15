import { useQuery } from '@tanstack/react-query';
import { api } from '../client';
import { qk } from '../keys';
import type { Timeline } from '../types';

/**
 * Zones of the objects over the last 26 weeks, one frame per week (the server's default period).
 * Loaded only while the time machine of the map is open.
 */
export function useTimeline(enabled: boolean) {
  return useQuery({
    queryKey: qk.timeline,
    queryFn: () => api<Timeline>('/dashboard/timeline'),
    enabled,
    staleTime: 5 * 60_000,
  });
}
