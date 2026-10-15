import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';
import { useObject } from '@/api/hooks/objects';
import { ApiError } from '@/api/client';
import { Button } from '@/components/ui/button';
import { EmptyState, QueryBoundary } from '@/components/QueryState';
import { ObjectCard } from './card/ObjectCard';

function ObjectNotFound() {
  const { t } = useTranslation('objects');
  return (
    <EmptyState
      action={
        <Button asChild variant="secondary" size="sm">
          <Link to="/objects">{t('card.notFound.back')}</Link>
        </Button>
      }
    >
      <strong>{t('card.notFound.title')}</strong>
      <br />
      {t('card.notFound.text')}
    </EmptyState>
  );
}

export function ObjectDetailPage() {
  const params = useParams();
  const id = Number(params.id);
  const validId = Number.isInteger(id) && id > 0;
  const query = useObject(id, validId);

  if (!validId || (query.error instanceof ApiError && query.error.status === 404)) {
    return <ObjectNotFound />;
  }
  return <QueryBoundary query={query}>{(object) => <ObjectCard object={object} />}</QueryBoundary>;
}
