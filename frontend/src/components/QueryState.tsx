import type { ReactNode } from 'react';
import { Button, Loader } from '@mantine/core';
import { IconAlertTriangle, IconInbox } from '@tabler/icons-react';
import type { UseQueryResult } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { errorMessage } from '@/api/queryClient';
import classes from './QueryState.module.css';

export function LoadingBlock({ label }: { label?: string }) {
  const { t } = useTranslation();
  return (
    <div className={classes.block} role="status" aria-live="polite">
      <Loader size="sm" />
      <span>{label ?? t('loading')}</span>
    </div>
  );
}

export function ErrorBlock({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <div className={classes.block} role="alert">
      <IconAlertTriangle size={22} stroke={1.6} />
      <strong>{t('states.loadError')}</strong>
      <span className={classes.detail}>{errorMessage(error)}</span>
      {onRetry && (
        <Button variant="default" size="xs" onClick={onRetry}>
          {t('retry')}
        </Button>
      )}
    </div>
  );
}

export function EmptyState({ children, action }: { children?: ReactNode; action?: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className={classes.block}>
      <IconInbox size={22} stroke={1.6} />
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
