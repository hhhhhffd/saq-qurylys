import type { ReactNode } from 'react';
import { Text } from '@mantine/core';
import { modals } from '@mantine/modals';
import i18n from '@/i18n';

interface ConfirmOptions {
  title: string;
  message: ReactNode;
  confirmLabel: string;
  /** red confirm button for irreversible actions */
  danger?: boolean;
  onConfirm: () => void;
}

/** Shared confirmation dialog; keep wording explicit about what will happen. */
export function confirmAction({ title, message, confirmLabel, danger, onConfirm }: ConfirmOptions) {
  modals.openConfirmModal({
    title,
    children: typeof message === 'string' ? <Text size="sm">{message}</Text> : message,
    labels: { confirm: confirmLabel, cancel: i18n.t('cancel', { ns: 'common' }) },
    confirmProps: danger ? { color: 'red' } : undefined,
    onConfirm,
  });
}
