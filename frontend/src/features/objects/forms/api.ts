import { useMutation, useQueryClient } from '@tanstack/react-query';
import { invalidateObjectData } from '@/api/hooks/objects';
import { api, toFormData } from '@/api/client';
import type { ObjectDocument } from '@/api/types';

/**
 * Attaches another screenshot or scan to an existing document (`POST /documents/{id}/evidence`).
 * `PATCH /documents/{id}` is JSON-only on the backend, so `useUpdateDocument` cannot carry a file.
 */
export function useAddDocumentEvidence() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) =>
      api<ObjectDocument>(`/documents/${id}/evidence`, { method: 'POST', body: toFormData({ file }) }),
    onSuccess: () => invalidateObjectData(qc),
    meta: { success: 'saved' },
  });
}
