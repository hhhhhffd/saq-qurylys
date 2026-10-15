import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, toFormData, unwrapList } from '../client';
import { qk } from '../keys';
import { invalidateObjectData } from './objects';
import type {
  AdDetail,
  AdListParams,
  AdPatch,
  AdRow,
  CaptureRequest,
  CollectorStatus,
  CollectQueued,
  ListResponse,
  Paged,
  Platform,
  SourceAccount,
  SourceAccountInput,
} from '../types';

const CAPTURE_POLL_MS = 3000;
// The worker collects after the request is queued; the page shows the outcome once it had time to finish.
const COLLECT_REFRESH_MS = 10_000;

export function useAds(params: AdListParams) {
  return useQuery({
    queryKey: qk.adList(params),
    queryFn: () => api<Paged<AdRow>>('/ads', { params: { ...params } }),
    placeholderData: keepPreviousData,
    // Captures run in a worker; keep polling while any item on the page is still pending.
    refetchInterval: (query) =>
      query.state.data?.items.some((ad) => ad.capture_status === 'pending') ? CAPTURE_POLL_MS : false,
  });
}

export function useAd(id: number | null | undefined) {
  return useQuery({
    queryKey: qk.ad(id ?? 0),
    queryFn: () => api<AdDetail>(`/ads/${id}`),
    enabled: id != null,
    refetchInterval: (query) => (query.state.data?.capture_status === 'pending' ? CAPTURE_POLL_MS : false),
  });
}

function invalidateAdData(qc: ReturnType<typeof useQueryClient>) {
  void qc.invalidateQueries({ queryKey: qk.ads });
  invalidateObjectData(qc);
}

export function useCaptureAd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: CaptureRequest) => api<AdDetail>('/ads/capture', { method: 'POST', body: data }),
    onSuccess: () => invalidateAdData(qc),
    meta: { success: 'captureQueued' },
  });
}

export interface ManualAdInput {
  text: string;
  platform: Platform;
  url?: string;
  object_id?: number | null;
  published_at?: string;
  is_outdoor: boolean;
  lat?: number;
  lon?: number;
  photos?: File[];
}

export function useCreateManualAd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ManualAdInput) => api<AdDetail>('/ads/manual', { method: 'POST', body: toFormData({ ...data }) }),
    onSuccess: () => invalidateAdData(qc),
    meta: { success: 'created' },
  });
}

export function useUpdateAd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: AdPatch }) =>
      api<AdDetail>(`/ads/${id}`, { method: 'PATCH', body: data }),
    onSuccess: () => invalidateAdData(qc),
    meta: { success: 'saved' },
  });
}

export function useConfirmHit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ adId, hitId, confirmed }: { adId: number; hitId: number; confirmed: boolean }) =>
      api<unknown>(`/ads/${adId}/hits/${hitId}/confirm`, { method: 'POST', body: { confirmed } }),
    onSuccess: () => invalidateAdData(qc),
  });
}

export function useAcceptLlm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (adId: number) => api<AdDetail>(`/ads/${adId}/accept-llm`, { method: 'POST' }),
    onSuccess: () => invalidateAdData(qc),
    meta: { success: 'saved' },
  });
}

// ---------------------------------------------------------------- source accounts

export function useSourceAccounts() {
  return useQuery({
    queryKey: qk.sourceAccounts,
    queryFn: () => api<ListResponse<SourceAccount>>('/source-accounts').then(unwrapList),
  });
}

export function useCreateSourceAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: SourceAccountInput) => api<SourceAccount>('/source-accounts', { method: 'POST', body: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.sourceAccounts }),
    meta: { success: 'created' },
  });
}

export function useUpdateSourceAccount() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<SourceAccountInput> }) =>
      api<SourceAccount>(`/source-accounts/${id}`, { method: 'PATCH', body: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.sourceAccounts }),
    meta: { success: 'saved' },
  });
}

export function useCollectors() {
  return useQuery({
    queryKey: qk.sourceCollectors,
    queryFn: () => api<CollectorStatus[]>('/source-accounts/collectors'),
  });
}

export function useCollectSourceNow() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<CollectQueued>(`/source-accounts/${id}/collect`, { method: 'POST' }),
    onSuccess: () => {
      setTimeout(() => {
        void qc.invalidateQueries({ queryKey: qk.sourceAccounts });
        void qc.invalidateQueries({ queryKey: qk.ads });
      }, COLLECT_REFRESH_MS);
    },
    meta: { success: 'collectQueued' },
  });
}
