import type { Complaint } from '@/api/types';

export interface ComplaintFormModalProps {
  opened: boolean;
  onClose: () => void;
  objectId: number;
  /** edit mode when provided (PATCH /complaints/{id}), create mode otherwise */
  complaint?: Complaint;
}

// Placeholder until implemented.
export function ComplaintFormModal(_props: ComplaintFormModalProps) {
  return null;
}
