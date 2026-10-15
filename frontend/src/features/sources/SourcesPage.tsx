import { useState } from 'react';
import { Button } from '@mantine/core';
import { IconArrowLeft, IconPlus } from '@tabler/icons-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useCollectors, useSourceAccounts } from '@/api/hooks/ads';
import { PageHeader } from '@/components/PageHeader';
import { Panel } from '@/components/Panel';
import { QueryBoundary } from '@/components/QueryState';
import { CollectorBadges } from './CollectorBadges';
import { SourceFormModal } from './SourceFormModal';
import { SourcesTable } from './SourcesTable';
import classes from './SourcesPage.module.css';

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
            <Button variant="default" component={Link} to="/ads" leftSection={<IconArrowLeft size={16} stroke={1.8} />}>
              {t('backToAds')}
            </Button>
            <Button leftSection={<IconPlus size={16} stroke={1.8} />} onClick={() => setAdding(true)}>
              {t('add')}
            </Button>
          </>
        }
      />
      <div className={classes.stack}>
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
