import { toast as sonner } from 'sonner';

interface ToastOptions {
  /** bold first line; `message` then goes under it as the description */
  title?: string;
}

function show(kind: 'success' | 'error' | 'info', message: string, { title }: ToastOptions = {}) {
  if (title) return sonner[kind](title, { description: message });
  return sonner[kind](message);
}

/**
 * App toasts (replaces `notifications.show`). The `Toaster` is mounted in Providers.tsx.
 *
 *   toast.success(t('toasts.saved'));
 *   toast.error(errorMessage(error), { title: t('error') });
 */
export const toast = {
  success: (message: string, options?: ToastOptions) => show('success', message, options),
  error: (message: string, options?: ToastOptions) => show('error', message, options),
  info: (message: string, options?: ToastOptions) => show('info', message, options),
};
