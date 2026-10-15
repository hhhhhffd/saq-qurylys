import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

interface ConfirmOptions {
  title: string;
  message: ReactNode;
  confirmLabel: string;
  /** red confirm button for irreversible actions */
  danger?: boolean;
  onConfirm: () => void;
}

let show: ((options: ConfirmOptions) => void) | null = null;

/** Shared confirmation dialog; keep wording explicit about what will happen. Needs `ConfirmProvider` (Providers.tsx). */
// eslint-disable-next-line react-refresh/only-export-components -- the helper and its provider are one unit
export function confirmAction(options: ConfirmOptions) {
  if (!show) throw new Error('ConfirmProvider is not mounted');
  show(options);
}

/** Renders the dialog of `confirmAction`. Mount once. */
export function ConfirmProvider() {
  const { t } = useTranslation();
  const [options, setOptions] = useState<ConfirmOptions | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    show = (next) => {
      setOptions(next);
      setOpen(true);
    };
    return () => {
      show = null;
    };
  }, []);

  // `options` stays after closing so the dialog does not go empty during its exit animation.
  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{options?.title}</AlertDialogTitle>
        </AlertDialogHeader>
        <AlertDialogDescription asChild>
          <div>{options?.message}</div>
        </AlertDialogDescription>
        <AlertDialogFooter>
          <AlertDialogCancel>{t('cancel')}</AlertDialogCancel>
          <AlertDialogAction variant={options?.danger ? 'destructive' : 'default'} onClick={() => options?.onConfirm()}>
            {options?.confirmLabel}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
