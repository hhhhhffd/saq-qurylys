import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { api } from '../client';
import { qk } from '../keys';
import type { SearchResults } from '../types';

export const SEARCH_MIN_LENGTH = 2;

export function useGlobalSearch(query: string) {
  return useQuery({
    queryKey: qk.search(query),
    queryFn: ({ signal }) => api<SearchResults>('/search', { params: { q: query }, signal }),
    enabled: query.length >= SEARCH_MIN_LENGTH,
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
}
