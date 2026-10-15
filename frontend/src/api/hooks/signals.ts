import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import { qk } from '../keys';
import type { Paged, SignalDetail, SignalListParams, SignalPatch, SignalRecipient, SignalRow } from '../types';

export function useSignals(params: SignalListParams) {
  return useQuery({
    queryKey: qk.signalList(params),
    queryFn: () => api<Paged<SignalRow>>('/signals', { params: { ...params } }),
    placeholderData: keepPreviousData,
  });
}

export function useSignal(id: number) {
  return useQuery({
    queryKey: qk.signal(id),
    queryFn: () => api<SignalDetail>(`/signals/${id}`),
  });
}

function useSignalMutation<TVars>(
  fn: (vars: TVars) => Promise<SignalDetail>,
  success: string,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.signals });
      void qc.invalidateQueries({ queryKey: ['audit'] });
      void qc.invalidateQueries({ queryKey: qk.notifications });
    },
    meta: { success },
  });
}

export function useCreateSignal() {
  return useSignalMutation(
    (objectId: number) => api<SignalDetail>('/signals', { method: 'POST', body: { object_id: objectId } }),
    'created',
  );
}

export function useUpdateSignal() {
  return useSignalMutation(
    ({ id, data }: { id: number; data: SignalPatch }) =>
      api<SignalDetail>(`/signals/${id}`, { method: 'PATCH', body: data }),
    'saved',
  );
}

/** The only path that sends a card to an external body; the UI must confirm explicitly first. */
export function useConfirmAndSend() {
  return useSignalMutation(
    ({ id, recipient }: { id: number; recipient: SignalRecipient }) =>
      api<SignalDetail>(`/signals/${id}/confirm-and-send`, { method: 'POST', body: { recipient } }),
    'sent',
  );
}

export function useReturnSignal() {
  return useSignalMutation(
    ({ id, comment }: { id: number; comment: string }) =>
      api<SignalDetail>(`/signals/${id}/return`, { method: 'POST', body: { comment } }),
    'returned',
  );
}

export function useRespondSignal() {
  return useSignalMutation(
    ({ id, response_text }: { id: number; response_text: string }) =>
      api<SignalDetail>(`/signals/${id}/response`, { method: 'POST', body: { response_text } }),
    'responded',
  );
}

export function useCloseSignal() {
  return useSignalMutation(
    (id: number) => api<SignalDetail>(`/signals/${id}/close`, { method: 'POST' }),
    'closed',
  );
}
