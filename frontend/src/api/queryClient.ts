import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';
import i18n from '@/i18n';
import { toast } from '@/lib/toast';
import { ApiError } from './client';

declare module '@tanstack/react-query' {
  interface Register {
    mutationMeta: {
      /** i18n key under `common:toasts.*` shown on success, e.g. `saved` */
      success?: string;
      /** suppress the automatic error toast (the caller renders the error itself) */
      silent?: boolean;
    };
    queryMeta: {
      /** show an error toast when this query fails (default: components render errors inline) */
      toast?: boolean;
    };
  }
}

/** Backend error codes are translated when we have a string; otherwise `detail.message` is shown. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return i18n.t(`errors.${error.code}`, { ns: 'common', defaultValue: error.message });
  }
  return error instanceof Error ? error.message : String(error);
}

function toastError(error: unknown) {
  if (error instanceof ApiError && error.status === 401) return; // handled by the login redirect
  toast.error(errorMessage(error), { title: i18n.t('error', { ns: 'common' }) });
}

export const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (error, query) => {
      if (query.meta?.toast) toastError(error);
    },
  }),
  mutationCache: new MutationCache({
    onError: (error, _variables, _context, mutation) => {
      if (!mutation.meta?.silent) toastError(error);
    },
    onSuccess: (_data, _variables, _context, mutation) => {
      const key = mutation.meta?.success;
      if (key) {
        toast.success(i18n.t(`toasts.${key}`, { ns: 'common' }));
      }
    },
  }),
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error) => {
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
        return failureCount < 1;
      },
    },
  },
});

// Evidence blobs are cached as object URLs; free them when the cache drops the entry.
queryClient.getQueryCache().subscribe((event) => {
  if (event.type === 'removed' && event.query.queryKey[0] === 'evidence') {
    const data = event.query.state.data as { url?: string } | undefined;
    if (data?.url) URL.revokeObjectURL(data.url);
  }
});
