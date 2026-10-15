import type { ReactNode } from 'react';
import { ActionIcon, VisuallyHidden } from '@mantine/core';
import { IconPencil, IconTrash } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import classes from './AdminPage.module.css';

/** Header for the trailing actions column: no visible text, but a name for screen readers. */
export function ActionsHeader() {
  const { t } = useTranslation();
  return <VisuallyHidden>{t('actions')}</VisuallyHidden>;
}

export function RowActions({ children }: { children: ReactNode }) {
  return <div className={classes.rowActions}>{children}</div>;
}

interface ButtonProps {
  label: string;
  onClick: () => void;
}

export function EditButton({ label, onClick }: ButtonProps) {
  return (
    <ActionIcon aria-label={label} onClick={onClick}>
      <IconPencil size={16} />
    </ActionIcon>
  );
}

export function DeleteButton({ label, onClick }: ButtonProps) {
  return (
    <ActionIcon aria-label={label} onClick={onClick}>
      <IconTrash size={16} />
    </ActionIcon>
  );
}
