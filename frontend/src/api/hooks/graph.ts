import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import { qk } from '../keys';
import type { GraphParams, LinkGraph, SourceAccount, SourceSuggestion, SuggestionDismissInput } from '../types';

export function useLinkGraph(params: GraphParams) {
  return useQuery({
    queryKey: qk.graph(params),
    queryFn: () => api<LinkGraph>('/graph', { params: { ...params } }),
    placeholderData: keepPreviousData,
  });
}

export function useSourceSuggestions() {
  return useQuery({
    queryKey: qk.sourceSuggestions,
    queryFn: () => api<SourceSuggestion[]>('/source-suggestions'),
  });
}

/** Accepting a candidate is an ordinary new source account (SPEC 10.3). */
export function useAcceptSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ platform, url }: Pick<SourceSuggestion, 'platform' | 'handle' | 'url'>) =>
      api<SourceAccount>('/source-accounts', { method: 'POST', body: { platform, url } }),
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: qk.sourceSuggestions }),
        qc.invalidateQueries({ queryKey: qk.sourceAccounts }),
      ]),
    meta: { success: 'created' },
  });
}

export function useDismissSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: SuggestionDismissInput) =>
      api<void>('/source-suggestions/dismiss', { method: 'POST', body: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.sourceSuggestions }),
  });
}
