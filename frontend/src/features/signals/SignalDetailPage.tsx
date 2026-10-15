import { Button } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';
import { ApiError } from '@/api/client';
import { useSignal } from '@/api/hooks/signals';
import { EmptyState, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { SignalCard } from './SignalCard';

function NotFound() {
  const { t } = useTranslation('signals');
  return (
    <EmptyState
      action={
        <Button component={Link} to="/signals" variant="default">
          {t('detail.back')}
        </Button>
      }
    >
      {t('detail.notFound')}
    </EmptyState>
  );
}

function SignalLoader({ id }: { id: number }) {
  const query = useSignal(id);
  // A failed background refetch keeps showing the card that is already loaded.
  if (query.data) return <SignalCard detail={query.data} />;
  if (!query.isError) return <LoadingBlock />;
  if (query.error instanceof ApiError && query.error.status === 404) return <NotFound />;
  return <ErrorBlock error={query.error} onRetry={() => void query.refetch()} />;
}

export function SignalDetailPage() {
  const id = Number(useParams().id);
  if (!Number.isInteger(id) || id <= 0) return <NotFound />;
  return <SignalLoader key={id} id={id} />;
}
