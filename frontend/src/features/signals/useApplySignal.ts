import { useQueryClient } from '@tanstack/react-query';
import { qk } from '@/api/keys';
import type { SignalDetail } from '@/api/types';

/** Puts the card returned by a mutation into the cache so the new status shows without waiting for a refetch. */
export function useApplySignal() {
  const queryClient = useQueryClient();
  return (next: SignalDetail) => queryClient.setQueryData(qk.signal(next.id), next);
}
