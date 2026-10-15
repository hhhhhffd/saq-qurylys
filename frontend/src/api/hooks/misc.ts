import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api, apiBlob, unwrapList } from '../client';
import { qk } from '../keys';
import type { AppNotification, AuditEntry, EvidenceMeta, ListResponse } from '../types';

// ---------------------------------------------------------------- notifications

/** The bell shows unread notifications and polls every 60 seconds (SPEC §8). */
export function useNotifications(enabled: boolean) {
  return useQuery({
    queryKey: qk.notifications,
    queryFn: () => api<ListResponse<AppNotification>>('/notifications', { params: { unread: true } }).then(unwrapList),
    enabled,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/notifications/${id}/read`, { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.notifications }),
  });
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<void>('/notifications/read-all', { method: 'POST' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.notifications }),
  });
}

// ---------------------------------------------------------------- audit

export function useAudit(entityType: string, entityId: number, enabled = true) {
  return useQuery({
    queryKey: qk.audit(entityType, entityId),
    queryFn: () =>
      api<ListResponse<AuditEntry>>('/audit', { params: { entity_type: entityType, entity_id: entityId } }).then(
        unwrapList,
      ),
    enabled,
  });
}

// ---------------------------------------------------------------- evidence

export function useEvidenceMeta(id: number | null | undefined) {
  return useQuery({
    queryKey: qk.evidenceMeta(id ?? 0),
    queryFn: () => api<EvidenceMeta>(`/evidence/${id}`),
    enabled: id != null,
    staleTime: Infinity,
  });
}

/**
 * Evidence content needs the Bearer header, so it is fetched as a blob and exposed
 * as an object URL (created in the query function, revoked when the cache entry is removed).
 */
export function useEvidenceContent(id: number | null | undefined) {
  return useQuery({
    queryKey: qk.evidenceBlob(id ?? 0),
    queryFn: async ({ signal }) => {
      const blob = await apiBlob(`/evidence/${id}/content`, signal);
      return { blob, url: URL.createObjectURL(blob) };
    },
    enabled: id != null,
    staleTime: Infinity,
    gcTime: 10 * 60_000,
  });
}
