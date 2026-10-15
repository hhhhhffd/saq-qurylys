import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { api, toFormData, unwrapList } from '../client';
import { qk } from '../keys';
import type {
  Complaint,
  ComplaintInput,
  Dashboard,
  Developer,
  DeveloperInput,
  DocumentInput,
  ImportResult,
  Inspection,
  InspectionInput,
  LinkedEntity,
  LinkedEntityInput,
  ListResponse,
  ObjectDetail,
  ObjectDocument,
  ObjectInput,
  ObjectListParams,
  ObjectRow,
  Paged,
  ScoreHistoryItem,
} from '../types';

/** Anything that can change a score or a card: registry data, ads, signals, dashboard counters. */
export function invalidateObjectData(qc: QueryClient) {
  void qc.invalidateQueries({ queryKey: qk.objects });
  void qc.invalidateQueries({ queryKey: ['dashboard'] });
}

// ---------------------------------------------------------------- dashboard

export interface DashboardParams {
  territory_id?: number;
  district_id?: number;
}

export function useDashboard(params: DashboardParams) {
  return useQuery({
    queryKey: qk.dashboard(params),
    queryFn: () => api<Dashboard>('/dashboard', { params: { ...params } }),
    placeholderData: keepPreviousData,
    refetchInterval: 5 * 60_000,
  });
}

// ---------------------------------------------------------------- objects

export function useObjects(params: ObjectListParams) {
  return useQuery({
    queryKey: qk.objectList(params),
    queryFn: () => api<Paged<ObjectRow>>('/objects', { params: { ...params } }),
    placeholderData: keepPreviousData,
  });
}

export function useObject(id: number, enabled = true) {
  return useQuery({
    queryKey: qk.object(id),
    queryFn: () => api<ObjectDetail>(`/objects/${id}`),
    enabled,
  });
}

export function useScoreHistory(id: number) {
  return useQuery({
    queryKey: qk.scoreHistory(id),
    queryFn: () => api<ListResponse<ScoreHistoryItem>>(`/objects/${id}/score-history`).then(unwrapList),
  });
}

export function useCreateObject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ObjectInput) => api<ObjectDetail>('/objects', { method: 'POST', body: data }),
    onSuccess: () => invalidateObjectData(qc),
    meta: { success: 'created' },
  });
}

export function useUpdateObject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ObjectInput }) =>
      api<ObjectDetail>(`/objects/${id}`, { method: 'PATCH', body: data }),
    onSuccess: () => invalidateObjectData(qc),
    meta: { success: 'saved' },
  });
}

export function useRecalculateObject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<unknown>(`/objects/${id}/recalculate`, { method: 'POST' }),
    onSuccess: () => invalidateObjectData(qc),
    meta: { success: 'recalculated' },
  });
}

export function useImportObjects() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api<ImportResult>('/objects/import', { method: 'POST', body: toFormData({ file }) }),
    onSuccess: () => invalidateObjectData(qc),
  });
}

export function useImportComplaints() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) =>
      api<ImportResult>('/complaints/import', { method: 'POST', body: toFormData({ file }) }),
    onSuccess: () => invalidateObjectData(qc),
  });
}

// ---------------------------------------------------------------- developers

export function useDevelopers(q?: string) {
  return useQuery({
    queryKey: [...qk.developers, q ?? ''],
    queryFn: () => api<ListResponse<Developer>>('/developers', { params: { q, limit: 50 } }).then(unwrapList),
    placeholderData: keepPreviousData,
  });
}

export function useCreateDeveloper() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: DeveloperInput) => api<Developer>('/developers', { method: 'POST', body: data }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.developers }),
    meta: { success: 'created' },
  });
}

export function useUpdateDeveloper() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<DeveloperInput> }) =>
      api<Developer>(`/developers/${id}`, { method: 'PATCH', body: data }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.developers });
      invalidateObjectData(qc);
    },
    meta: { success: 'saved' },
  });
}

// ---------------------------------------------------------------- documents

export function useCreateDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ objectId, data, file }: { objectId: number; data: DocumentInput; file?: File | null }) =>
      api<ObjectDocument>(`/objects/${objectId}/documents`, {
        method: 'POST',
        body: toFormData({ ...data, file }),
      }),
    onSuccess: () => invalidateObjectData(qc),
    meta: { success: 'created' },
  });
}

/** JSON patch; becomes multipart when a screenshot/scan file is attached. */
export function useUpdateDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data, file }: { id: number; data: Partial<DocumentInput>; file?: File | null }) =>
      api<ObjectDocument>(`/documents/${id}`, {
        method: 'PATCH',
        body: file ? toFormData({ ...data, file }) : data,
      }),
    onSuccess: () => invalidateObjectData(qc),
    meta: { success: 'saved' },
  });
}

// ---------------------------------------------------------------- inspections

export function useCreateInspection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ objectId, data, photos }: { objectId: number; data: InspectionInput; photos?: File[] }) =>
      api<Inspection>(`/objects/${objectId}/inspections`, {
        method: 'POST',
        body: toFormData({ ...data, photos }),
      }),
    onSuccess: () => invalidateObjectData(qc),
    meta: { success: 'created' },
  });
}

// ---------------------------------------------------------------- complaints

export function useCreateComplaint() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ objectId, data }: { objectId: number; data: ComplaintInput }) =>
      api<Complaint>(`/objects/${objectId}/complaints`, { method: 'POST', body: data }),
    onSuccess: () => invalidateObjectData(qc),
    meta: { success: 'created' },
  });
}

export function useUpdateComplaint() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<ComplaintInput> }) =>
      api<Complaint>(`/complaints/${id}`, { method: 'PATCH', body: data }),
    onSuccess: () => invalidateObjectData(qc),
    meta: { success: 'saved' },
  });
}

// ---------------------------------------------------------------- linked entities

export function useCreateLinkedEntity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ objectId, data }: { objectId: number; data: LinkedEntityInput }) =>
      api<LinkedEntity>(`/objects/${objectId}/linked-entities`, { method: 'POST', body: data }),
    onSuccess: () => invalidateObjectData(qc),
    meta: { success: 'created' },
  });
}

export function useDeleteLinkedEntity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/linked-entities/${id}`, { method: 'DELETE' }),
    onSuccess: () => invalidateObjectData(qc),
    meta: { success: 'deleted' },
  });
}
