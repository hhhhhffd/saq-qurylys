import type { ObjectDetail } from '@/api/types';

export interface ObjectFormModalProps {
  opened: boolean;
  onClose: () => void;
  /** edit mode when provided, create mode otherwise */
  object?: ObjectDetail;
}

// Placeholder until implemented.
export function ObjectFormModal(_props: ObjectFormModalProps) {
  return null;
}
