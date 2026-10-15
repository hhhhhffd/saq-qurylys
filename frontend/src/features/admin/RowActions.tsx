import type { ReactNode } from 'react';
import { IconPencil, IconTrash } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';

/** Header for the trailing actions column: no visible text, but a name for screen readers. */
export function ActionsHeader() {
  const { t } = useTranslation();
  return <span className="sr-only">{t('actions')}</span>;
}

export function RowActions({ children }: { children: ReactNode }) {
  return <div className="flex min-w-16 items-center justify-end gap-1">{children}</div>;
}

interface ButtonProps {
  label: string;
  onClick: () => void;
}

export function EditButton({ label, onClick }: ButtonProps) {
  return (
    <Button variant="ghost" size="icon-sm" aria-label={label} onClick={onClick}>
      <IconPencil />
    </Button>
  );
}

export function DeleteButton({ label, onClick }: ButtonProps) {
  return (
    <Button variant="ghost" size="icon-sm" aria-label={label} onClick={onClick}>
      <IconTrash />
    </Button>
  );
}
