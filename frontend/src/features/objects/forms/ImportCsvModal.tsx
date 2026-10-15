export interface ImportCsvModalProps {
  opened: boolean;
  onClose: () => void;
  /** `POST /objects/import` or `POST /complaints/import` */
  kind: 'objects' | 'complaints';
}

// Placeholder until implemented.
export function ImportCsvModal(_props: ImportCsvModalProps) {
  return null;
}
