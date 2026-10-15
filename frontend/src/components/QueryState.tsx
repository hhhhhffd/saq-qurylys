import type { ReactNode } from 'react';
import { IconAlertTriangle, IconInbox } from '@tabler/icons-react';
import type { UseQueryResult } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { errorMessage } from '@/api/queryClient';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';

const blockClass = 'flex flex-col items-center justify-center gap-2 px-4 py-9 text-center text-sm text-text-2';

export function LoadingBlock({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className={blockClass} role="status" aria-live="polite">
      <Spinner role="presentation" aria-hidden className="text-accent-text" />
      <span>{label ?? t('loading')}</span>
    </div>
  );
}

export function ErrorBlock({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <div className={blockClass} role="alert">
      <IconAlertTriangle size={22} stroke={1.6} className="text-zone-red-ink" />
      <strong className="text-text">{t('states.loadError')}</strong>
      <span className="max-w-[460px] text-text-3">{errorMessage(error)}</span>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          {t('retry')}
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ children, action }: { children?: ReactNode; action?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className={blockClass}>
      <IconInbox size={22} stroke={1.6} className="text-text-3" />
      <span>{children ?? t('states.empty')}</span>
      {action}
    </div>
  );
}

interface BoundaryProps<T> {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
}

/** Loading and error states for a query; children render only once data exists. */
export function QueryBoundary<T>({ query, children }: BoundaryProps<T>) {
  if (query.isPending) return <LoadingBlock />;
  if (query.isError) return <ErrorBlock error={query.error} onRetry={() => void query.refetch()} />;
  return <>{children(query.data)}</>;
}
