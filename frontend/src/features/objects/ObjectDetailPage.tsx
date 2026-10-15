import { Button } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';
import { useObject } from '@/api/hooks/objects';
import { ApiError } from '@/api/client';
import { EmptyState, QueryBoundary } from '@/components/QueryState';
import { ObjectCard } from './card/ObjectCard';

function ObjectNotFound() {
  const { t } = useTranslation('objects');
  return (
    <EmptyState
      action={
        <Button component={Link} to="/objects" variant="default" size="xs">
          {t('card.notFound.back')}
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
