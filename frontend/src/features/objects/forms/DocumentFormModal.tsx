import type { ObjectDocument } from '@/api/types';

export interface DocumentFormModalProps {
  opened: boolean;
  onClose: () => void;
  objectId: number;
  /** edit mode when provided (PATCH /documents/{id}), create mode otherwise */
  document?: ObjectDocument;
}

// Placeholder until implemented.
export function DocumentFormModal(_props: DocumentFormModalProps) {
  return null;
}
