import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '../client';
import { qk } from '../keys';
import type { Assignee, Assignment, AssignmentCreate, AssignmentListParams, AssignmentPatch, Paged } from '../types';

export function useAssignments(params: AssignmentListParams) {
  return useQuery({
    queryKey: qk.assignmentList(params),
    queryFn: () => api<Paged<Assignment>>('/assignments', { params: { ...params } }),
    placeholderData: keepPreviousData,
  });
}

export function useObjectAssignments(objectId: number) {
  return useQuery({
    queryKey: qk.objectAssignments(objectId),
    queryFn: () => api<Assignment[]>(`/objects/${objectId}/assignments`),
  });
}

export function useAssignees(objectId: number, enabled: boolean) {
  return useQuery({
    queryKey: qk.assignees(objectId),
    queryFn: () => api<Assignee[]>('/assignments/assignees', { params: { object_id: objectId } }),
    enabled,
  });
}

export function useCreateAssignment(objectId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AssignmentCreate) =>
      api<Assignment>(`/objects/${objectId}/assignments`, { method: 'POST', body: data }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.assignments });
      void qc.invalidateQueries({ queryKey: ['audit'] });
    },
    meta: { success: 'created' },
  });
}

export function useUpdateAssignment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: AssignmentPatch }) =>
      api<Assignment>(`/assignments/${id}`, { method: 'PATCH', body: data }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: qk.assignments });
      void qc.invalidateQueries({ queryKey: ['audit'] });
    },
    meta: { success: 'saved' },
  });
}
