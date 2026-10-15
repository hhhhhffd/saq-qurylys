import type { Developer } from '@/api/types';

export interface DeveloperFormModalProps {
  opened: boolean;
  onClose: () => void;
  /** edit mode when provided (PATCH /developers/{id}), create mode otherwise */
  developer?: Developer;
  /** called with the created/updated developer (used by ObjectFormModal to select a new developer) */
  onSaved?: (developer: Developer) => void;
}

// Placeholder until implemented.
export function DeveloperFormModal(_props: DeveloperFormModalProps) {
  return null;
}
