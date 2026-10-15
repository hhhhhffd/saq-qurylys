import { useState } from 'react';
import { IconArrowLeft, IconPlus } from '@tabler/icons-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useCollectors, useSourceAccounts } from '@/api/hooks/ads';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/PageHeader';
import { Panel } from '@/components/Panel';
import { QueryBoundary } from '@/components/QueryState';
import { CollectorBadges } from './CollectorBadges';
import { SourceFormModal } from './SourceFormModal';
import { SourcesTable } from './SourcesTable';

export function SourcesPage() {
  const { t } = useTranslation('sources');
  const accounts = useSourceAccounts();
  const collectors = useCollectors();
  const [adding, setAdding] = useState(false);

  return (
    <>
      <PageHeader
        title={t('title')}
        subtitle={t('subtitle')}
        actions={
          <>
            <Button variant="secondary" asChild>
              <Link to="/ads">
                <IconArrowLeft />
                {t('backToAds')}
              </Link>
            </Button>
            <Button onClick={() => setAdding(true)}>
              <IconPlus />
              {t('add')}
            </Button>
          </>
        }
      />
      <div className="flex flex-col gap-5">
        <Panel title={t('collectors.title')}>
          <QueryBoundary query={collectors}>{(items) => <CollectorBadges collectors={items} />}</QueryBoundary>
        </Panel>
        <QueryBoundary query={accounts}>
          {(rows) => <SourcesTable accounts={rows} collectors={collectors.data} />}
        </QueryBoundary>
      </div>
      {adding && <SourceFormModal onClose={() => setAdding(false)} />}
    </>
  );
}
