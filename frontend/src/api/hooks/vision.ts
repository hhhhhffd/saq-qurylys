import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth/useAuth';
import { api, apiBlob, ApiError } from '../client';
import { qk } from '../keys';
import type {
  FindingReviewAction,
  FindingStatus,
  Paged,
  VisionAsset,
  VisionConfig,
  VisionFinding,
  VisionFindingInput,
  VisionFrame,
  VisionSessionDetail,
  VisionSessionInput,
  VisionSessionListItem,
  VisionSessionListParams,
  VisionSource,
} from '../types';

const POLL_MS = 3000;
export const FRAMES_PAGE_SIZE = 24;

/** The module is optional: a 404 on its config means it is switched off. The query resolves to `null` then. */
export function useVisionConfig(enabled = true) {
  return useQuery({
    queryKey: qk.visionConfig,
    queryFn: async () => {
      try {
        return await api<VisionConfig>('/vision/config');
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null;
        throw error;
      }
    },
    enabled,
    retry: false,
    staleTime: 5 * 60_000,
  });
}

/** True only once the config arrived and says the module is on (nav tab and the object card panel); the module is for registry editors. */
export function useVisionEnabled(): boolean {
  const { canEditRegistry } = useAuth();
  const { data } = useVisionConfig(canEditRegistry);
  return data?.enabled === true;
}

export function useVisionSessions(params: VisionSessionListParams) {
  return useQuery({
    queryKey: qk.visionSessions(params),
    queryFn: () => api<Paged<VisionSessionListItem>>('/vision/sessions', { params: { ...params } }),
    placeholderData: keepPreviousData,
    refetchInterval: (query) => (query.state.data?.items.some((item) => item.processing) ? POLL_MS : false),
  });
}

/** An asset still being worked on, a detector run that has not finished, or an OCR run that has not finished. */
const isWorking = (session: VisionSessionDetail) =>
  session.processing ||
  session.assets.some((asset) => asset.status === 'queued' || asset.status === 'processing') ||
  session.runs.some((run) => run.status === 'queued' || run.status === 'running') ||
  session.findings.some((finding) => finding.ocr_status === 'pending');

export function useVisionSession(id: number) {
  return useQuery({
    queryKey: qk.visionSession(id),
    queryFn: () => api<VisionSessionDetail>(`/vision/sessions/${id}`),
    refetchInterval: (query) => (query.state.data && isWorking(query.state.data) ? POLL_MS : false),
  });
}

export function useVisionFrames(sessionId: number, page: number, processing: boolean) {
  return useQuery({
    queryKey: qk.visionFrames(sessionId, page),
    queryFn: () =>
      api<Paged<VisionFrame>>(`/vision/sessions/${sessionId}/frames`, {
        params: { limit: FRAMES_PAGE_SIZE, offset: page * FRAMES_PAGE_SIZE },
      }),
    placeholderData: keepPreviousData,
    // New frames appear while videos are being processed.
    refetchInterval: processing ? POLL_MS : false,
  });
}

/** Frame content needs the Bearer header, so it is a blob exposed as an object URL (revoked in queryClient). */
export function useFrameImage(frameId: number | null, variant: 'preview' | 'original') {
  return useQuery({
    queryKey: qk.visionBlob('frame', frameId ?? 0, variant),
    queryFn: async ({ signal }) => {
      const blob = await apiBlob(`/vision/frames/${frameId}/content?variant=${variant}`, signal);
      return { blob, url: URL.createObjectURL(blob) };
    },
    enabled: frameId != null,
    staleTime: Infinity,
    gcTime: 5 * 60_000,
  });
}

function useInvalidateVision() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: qk.vision });
}

export function useCreateVisionSession() {
  const invalidate = useInvalidateVision();
  return useMutation({
    mutationFn: (data: VisionSessionInput & { source: VisionSource }) =>
      api<VisionSessionDetail>('/vision/sessions', { method: 'POST', body: data }),
    onSuccess: invalidate,
    meta: { success: 'visionSessionCreated' },
  });
}

export function useUpdateVisionSession(id: number) {
  const invalidate = useInvalidateVision();
  return useMutation({
    mutationFn: (data: VisionSessionInput) =>
      api<VisionSessionDetail>(`/vision/sessions/${id}`, { method: 'PATCH', body: data }),
    onSuccess: invalidate,
    meta: { success: 'saved' },
  });
}

export function useMarkSessionReviewed(id: number) {
  const invalidate = useInvalidateVision();
  return useMutation({
    mutationFn: () => api<VisionSessionDetail>(`/vision/sessions/${id}/reviewed`, { method: 'POST' }),
    onSuccess: invalidate,
    meta: { success: 'visionReviewed' },
  });
}

export function useReanalyzeSession(id: number) {
  const invalidate = useInvalidateVision();
  return useMutation({
    mutationFn: () => api<VisionSessionDetail>(`/vision/sessions/${id}/reanalyze`, { method: 'POST' }),
    onSuccess: invalidate,
    meta: { success: 'visionReanalysisQueued' },
  });
}

export function useRetryAsset() {
  const invalidate = useInvalidateVision();
  return useMutation({
    mutationFn: (assetId: number) => api<VisionAsset>(`/vision/assets/${assetId}/retry`, { method: 'POST' }),
    onSuccess: invalidate,
  });
}

export function useCreateFinding(sessionId: number) {
  const invalidate = useInvalidateVision();
  return useMutation({
    mutationFn: (data: VisionFindingInput) =>
      api<VisionFinding>(`/vision/sessions/${sessionId}/findings`, { method: 'POST', body: data }),
    onSuccess: invalidate,
    meta: { success: 'created' },
  });
}

export function useReviewFinding() {
  const invalidate = useInvalidateVision();
  return useMutation({
    mutationFn: ({ id, action, comment, status }: { id: number; action: FindingReviewAction; comment?: string; status?: FindingStatus }) =>
      api<VisionFinding>(`/vision/findings/${id}/review`, { method: 'POST', body: { action, comment, status } }),
    onSuccess: invalidate,
    meta: { success: 'saved' },
  });
}

export function useRunOcr() {
  const invalidate = useInvalidateVision();
  return useMutation({
    mutationFn: (id: number) => api<VisionFinding>(`/vision/findings/${id}/ocr`, { method: 'POST' }),
    onSuccess: invalidate,
  });
}

export function usePublishAd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, text, object_id }: { id: number; text: string; object_id?: number | null }) =>
      api<{ ad_id: number }>(`/vision/findings/${id}/publish-ad`, { method: 'POST', body: { text, object_id } }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.vision });
      void qc.invalidateQueries({ queryKey: qk.ads });
    },
    meta: { success: 'visionAdCreated' },
  });
}
