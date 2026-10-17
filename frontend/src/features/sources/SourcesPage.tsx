import { useState } from 'react';
import { IconAlertTriangle, IconArrowLeft, IconPlus } from '@tabler/icons-react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useCollectors, useSourceAccounts } from '@/api/hooks/ads';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/PageHeader';
import { QueryBoundary } from '@/components/QueryState';
import { COLLECTOR_SOURCES, isCollectorOn } from './collectors';
import { CollectorBadges } from './CollectorBadges';
import { SourceFormModal } from './SourceFormModal';
import { SourcesTable } from './SourcesTable';

export function SourcesPage() {
  const { t } = useTranslation('sources');
  const accounts = useSourceAccounts();
  const collectors = useCollectors();
  const [adding, setAdding] = useState(false);
  const collectorStatuses = collectors.data;
  const enabledCount = collectorStatuses
    ? COLLECTOR_SOURCES.filter((source) => isCollectorOn(source, collectorStatuses)).length
    : 0;
  const disabledCount = COLLECTOR_SOURCES.length - enabledCount;

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
            <Button className="max-sm:min-h-11" onClick={() => setAdding(true)}>
              <IconPlus />
              {t('add')}
            </Button>
          </>
        }
      />
      <div className="flex flex-col gap-5">
        <section
          className={
            collectors.data && disabledCount > 0
              ? 'flex flex-col gap-2 rounded border border-zone-yellow/40 bg-zone-yellow-bg px-3.5 py-3 sm:flex-row sm:items-center sm:justify-between'
              : 'flex flex-col gap-2 rounded border border-border bg-surface px-3.5 py-3 sm:flex-row sm:items-center sm:justify-between'
          }
          aria-label={t('collectors.title')}
        >
          {collectors.data ? (
            <div className="min-w-0">
              <p className="m-0 text-sm font-semibold">{t('collectors.summary', { enabled: enabledCount, total: COLLECTOR_SOURCES.length })}</p>
              {disabledCount > 0 && <p className="mb-0 mt-1 text-sm text-text-2">{t('collectors.offHint')}</p>}
            </div>
          ) : collectors.isPending ? (
            <p className="m-0 text-sm text-text-2" role="status">{t('collectors.loading')}</p>
          ) : null}
          {collectors.data && disabledCount > 0 && (
            <Button className="shrink-0 max-sm:min-h-11" variant="secondary" size="sm" asChild>
              <Link to="/ads">{t('collectors.manualAdd')}</Link>
            </Button>
          )}
          {collectors.isError && (
            <div className="flex flex-wrap items-center gap-2 text-sm text-zone-red-ink" role="alert">
              <IconAlertTriangle className="size-4 shrink-0" aria-hidden />
              <span>{t('collectors.loadError')}</span>
              <Button variant="secondary" size="xs" onClick={() => void collectors.refetch()}>
                {t('retry', { ns: 'common' })}
              </Button>
            </div>
          )}
        </section>
        <QueryBoundary query={accounts}>
          {(rows) => <SourcesTable accounts={rows} collectors={collectors.data} />}
        </QueryBoundary>
        <details className="rounded border border-border bg-surface px-3.5 py-3">
          <summary className="flex cursor-pointer items-center text-sm font-semibold text-text-2 hover:text-text max-sm:min-h-11">
            {collectors.data
              ? t('collectors.details', { enabled: enabledCount, total: COLLECTOR_SOURCES.length })
              : t('collectors.title')}
          </summary>
          <div className="mt-3 flex flex-col gap-2.5">
            <p className="m-0 text-sm text-text-2">{t('collectors.configNote')}</p>
            <QueryBoundary query={collectors}>{(items) => <CollectorBadges collectors={items} />}</QueryBoundary>
          </div>
        </details>
      </div>
      {adding && <SourceFormModal onClose={() => setAdding(false)} />}
    </>
  );
}
