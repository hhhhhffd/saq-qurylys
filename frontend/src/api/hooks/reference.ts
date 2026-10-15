import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, unwrapList } from '../client';
import { qk } from '../keys';
import type {
  AdminUser,
  AppSettings,
  DistrictCollection,
  Holiday,
  ListResponse,
  Phrase,
  PhraseInput,
  RiskFactor,
  RiskFactorChange,
  Territory,
  TerritoryInput,
  TerritoryUpdate,
  UserInput,
} from '../types';

// ---------------------------------------------------------------- territories

export function useTerritories() {
  return useQuery({
    queryKey: qk.territories,
    queryFn: () => api<ListResponse<Territory>>('/territories').then(unwrapList),
    staleTime: 5 * 60_000,
  });
}

export function useDistricts(territoryId: number | null | undefined) {
  return useQuery({
    queryKey: qk.districts(territoryId),
    queryFn: () => api<DistrictCollection>(`/territories/${territoryId}/districts`),
    enabled: territoryId != null,
    staleTime: 5 * 60_000,
  });
}

export function useCreateTerritory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: TerritoryInput) => api<Territory>('/territories', { method: 'POST', body: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.territories }),
    meta: { success: 'created' },
  });
}

export function useUpdateTerritory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: TerritoryUpdate }) =>
      api<Territory>(`/territories/${id}`, { method: 'PATCH', body: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.territories }),
    meta: { success: 'saved' },
  });
}

// ---------------------------------------------------------------- users

export function useUsers() {
  return useQuery({
    queryKey: qk.users,
    queryFn: () => api<ListResponse<AdminUser>>('/users').then(unwrapList),
  });
}

export function useCreateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: UserInput) => api<AdminUser>('/users', { method: 'POST', body: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.users }),
    meta: { success: 'created' },
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<UserInput> }) =>
      api<AdminUser>(`/users/${id}`, { method: 'PATCH', body: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.users }),
    meta: { success: 'saved' },
  });
}

// ---------------------------------------------------------------- settings

export function useSettings() {
  return useQuery({
    queryKey: qk.settings,
    queryFn: () => api<AppSettings>('/settings'),
    staleTime: 60_000,
  });
}

/** Partial update: only the given keys change. */
export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<AppSettings>) => api<AppSettings>('/settings', { method: 'PUT', body: data }),
    onSuccess: (settings) => qc.setQueryData(qk.settings, settings),
    meta: { success: 'saved' },
  });
}

// ---------------------------------------------------------------- holidays

export function useHolidays() {
  return useQuery({
    queryKey: qk.holidays,
    queryFn: () => api<ListResponse<Holiday>>('/holidays').then(unwrapList),
  });
}

export function useCreateHoliday() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: Holiday) => api<Holiday>('/holidays', { method: 'POST', body: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.holidays }),
    meta: { success: 'created' },
  });
}

export function useDeleteHoliday() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (day: string) => api<void>(`/holidays/${day}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.holidays }),
    meta: { success: 'deleted' },
  });
}

// ---------------------------------------------------------------- phrases

export function usePhrases() {
  return useQuery({
    queryKey: qk.phrases,
    queryFn: () => api<ListResponse<Phrase>>('/phrases', { params: { limit: 500 } }).then(unwrapList),
  });
}

export function useCreatePhrase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: PhraseInput) => api<Phrase>('/phrases', { method: 'POST', body: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.phrases }),
    meta: { success: 'created' },
  });
}

export function useUpdatePhrase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<PhraseInput> }) =>
      api<Phrase>(`/phrases/${id}`, { method: 'PATCH', body: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.phrases }),
    meta: { success: 'saved' },
  });
}

// ---------------------------------------------------------------- risk factors

export function useRiskFactors() {
  return useQuery({
    queryKey: qk.riskFactors,
    queryFn: () => api<ListResponse<RiskFactor>>('/risk-factors').then(unwrapList),
    staleTime: 60_000,
  });
}

export function useRiskFactorHistory() {
  return useQuery({
    queryKey: qk.riskFactorHistory,
    queryFn: () => api<ListResponse<RiskFactorChange>>('/risk-factors/history').then(unwrapList),
  });
}

export function useUpdateRiskFactor() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ code, data }: { code: string; data: Partial<Pick<RiskFactor, 'weight' | 'is_active' | 'description'>> }) =>
      api<RiskFactor>(`/risk-factors/${code}`, { method: 'PATCH', body: data }),
    onSuccess: () => {
      // A weight change triggers a recalculation of every object on the backend.
      void qc.invalidateQueries({ queryKey: qk.riskFactors });
      void qc.invalidateQueries({ queryKey: qk.objects });
      void qc.invalidateQueries({ queryKey: ['dashboard'] });
    },
    meta: { success: 'saved' },
  });
}
