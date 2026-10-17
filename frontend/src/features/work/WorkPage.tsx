import { IconArrowRight, IconChevronRight } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { useDashboard } from '@/api/hooks/objects';
import { useSignals } from '@/api/hooks/signals';
import type { SignalRow, SignalStatus } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { EmptyState, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { ReportCard } from './ReportCard';
import { MyAssignments } from './MyAssignments';

type QueueStatus = Exclude<SignalStatus, 'closed'>;
type SignalQuery = ReturnType<typeof useSignals>;

interface Queue {
  status: QueueStatus;
  title: string;
  actionLabel: string;
  query: SignalQuery;
}

function formatDate(value: string, language: string): string {
  const date = new Date(`${value.slice(0, 10)}T12:00:00`);
  return new Intl.DateTimeFormat(language === 'kk' ? 'kk-KZ' : 'ru-RU', {
    day: 'numeric',
    month: 'short',
  }).format(date);
}

function SignalLink({ row, language }: { row: SignalRow; language: string }) {
  const { t } = useTranslation();

  return (
    <Link
      to={`/signals/${row.id}`}
      aria-label={`${t('work.openCard')}: ${row.number}, ${row.object_name}`}
      className="flex min-h-11 items-center justify-between gap-3 rounded px-2 py-2 text-sm text-text no-underline transition-colors hover:bg-hover focus-visible:ring-2 focus-visible:ring-focus"
    >
      <span className="min-w-0">
        <span className="block font-semibold tabular-nums">{row.number}</span>
        <span className="block truncate text-text-2">{row.object_name}</span>
      </span>
      <span className="flex flex-none items-center gap-2 text-right text-xs">
        {row.is_overdue ? (
          <span className="text-zone-red-ink">{t('work.overdue')}</span>
        ) : row.due_date ? (
          <span className="text-text-3">{t('work.dueDate', { value: formatDate(row.due_date, language) })}</span>
        ) : null}
        <IconChevronRight className="size-4 text-text-3" aria-hidden />
      </span>
    </Link>
  );
}

export function WorkPage() {
  const { t, i18n } = useTranslation();
  const { isAdmin, canEditRegistry } = useAuth();
  const returned = useSignals({ status: 'returned', limit: 3 });
  const requiresConfirmation = useSignals({ status: 'requires_confirmation', limit: 3 });
  const responded = useSignals({ status: 'responded', limit: 3 });
  const sent = useSignals({ status: 'sent', limit: 3 });
  const dashboard = useDashboard({});

  const queues: Queue[] = [
    { status: 'returned', title: t('work.queueReturned'), actionLabel: 'work.primaryReturned', query: returned },
    {
      status: 'requires_confirmation',
      title: t('work.queueConfirmation'),
      actionLabel: 'work.primaryConfirmation',
      query: requiresConfirmation,
    },
    { status: 'responded', title: t('work.queueResponded'), actionLabel: 'work.primaryResponded', query: responded },
    { status: 'sent', title: t('work.queueSent'), actionLabel: 'work.primarySent', query: sent },
  ];
  const failedQueues = queues.filter(({ query }) => query.isError);
  const loadingQueues = queues.some(({ query }) => query.isPending);
  const populatedQueues = queues.filter(({ query }) => (query.data?.total ?? 0) > 0);
  const allQueuesEmpty =
    !loadingQueues &&
    failedQueues.length === 0 &&
    queues.every(({ query }) => query.data?.total === 0);
  const primaryQueue =
    !loadingQueues && failedQueues.length === 0
      ? queues.find(({ status, query }) => status !== 'sent' && (query.data?.total ?? 0) > 0) ??
        queues.find(({ status, query }) => status === 'sent' && (query.data?.total ?? 0) > 0)
      : undefined;
  const primarySignal =
    primaryQueue?.status === 'sent'
      ? primaryQueue.query.data?.items.find((row) => row.recipient === 'mio') ?? primaryQueue.query.data?.items[0]
      : primaryQueue?.query.data?.items[0];
  const primaryHref = isAdmin
    ? '/signals'
    : primaryQueue
      ? primarySignal
        ? `/signals/${primarySignal.id}`
        : `/signals?status=${primaryQueue.status}`
      : allQueuesEmpty
        ? '/ads'
        : undefined;
  const primaryLabel = isAdmin
    ? t('work.openCards')
    : primaryQueue
      ? primarySignal
        ? t(
            primaryQueue.status === 'sent' && primarySignal.recipient === 'mio'
              ? 'work.primarySentMio'
              : primaryQueue.actionLabel,
            { number: primarySignal.number },
          )
        : t('work.openAll')
      : allQueuesEmpty
        ? t('work.checkAds')
        : undefined;
  const redObjects = dashboard.data?.objects.filter((object) => object.zone === 'red').slice(0, 3) ?? [];

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-3xl space-y-2">
          <h1>{isAdmin ? t('work.adminTitle') : t('work.title')}</h1>
          <p className="m-0 text-sm text-text-2">{isAdmin ? t('work.adminIntro') : t('work.intro')}</p>
          {isAdmin && <p className="m-0 text-xs text-text-3">{t('work.adminReadOnly')}</p>}
        </div>
        {primaryHref && primaryLabel && (
          <Link
            to={primaryHref}
            className="inline-flex min-h-11 items-center justify-center rounded bg-primary px-4 text-sm font-semibold text-primary-foreground no-underline transition-colors hover:bg-accent-hover focus-visible:ring-2 focus-visible:ring-focus"
          >
            {primaryLabel}
          </Link>
        )}
      </header>

      {canEditRegistry && <MyAssignments />}

      <section className="border-y border-border py-3" aria-labelledby="work-journey-title">
        <h2 id="work-journey-title" className="mb-2 text-sm font-semibold">
          {t('work.journeyTitle')}
        </h2>
        <ol className="m-0 flex list-none flex-wrap items-center gap-1 p-0 text-sm" aria-label={t('work.journeyAria')}>
          <li>
            <Link to="/ads" className="inline-flex min-h-11 items-center rounded px-2 text-text-2 hover:bg-hover hover:text-text">
              {t('work.journeyAd')}
            </Link>
          </li>
          <li aria-hidden="true"><IconArrowRight className="size-4 text-text-3" /></li>
          <li>
            <Link to="/objects" className="inline-flex min-h-11 items-center rounded px-2 text-text-2 hover:bg-hover hover:text-text">
              {t('work.journeyObject')}
            </Link>
          </li>
          <li aria-hidden="true"><IconArrowRight className="size-4 text-text-3" /></li>
          <li>
            <Link to="/signals" className="inline-flex min-h-11 items-center rounded px-2 text-text-2 hover:bg-hover hover:text-text">
              {t('work.journeyCard')}
            </Link>
          </li>
          <li aria-hidden="true"><IconArrowRight className="size-4 text-text-3" /></li>
          <li className="px-2 text-text-2">{t('work.journeyResponse')}</li>
          <li aria-hidden="true"><IconArrowRight className="size-4 text-text-3" /></li>
          <li className="px-2 text-text-2">{t('work.journeyFinish')}</li>
        </ol>
      </section>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(16rem,0.38fr)]">
        <section aria-labelledby="work-queues-title" className="min-w-0 space-y-3">
          <h2 id="work-queues-title" className="text-lg font-semibold">
            {t('work.queuesTitle')}
          </h2>

          <div className="divide-y divide-border rounded border border-border bg-surface px-3">
            {failedQueues.length > 0 && (
              <div className="py-2">
                <ErrorBlock
                  error={failedQueues[0].query.error}
                  onRetry={() => failedQueues.forEach(({ query }) => void query.refetch())}
                />
              </div>
            )}
            {loadingQueues && <LoadingBlock label={t('work.loadingSignals')} />}
            {allQueuesEmpty && <EmptyState>{t('work.emptyQueue')}</EmptyState>}

            {populatedQueues.map(({ status, title, query }) => (
              <section key={status} className="py-3" aria-labelledby={`work-queue-${status}`}>
                <div className="flex items-center justify-between gap-3">
                  <h3 id={`work-queue-${status}`} className="text-sm font-semibold text-text">
                    {title}
                  </h3>
                  <span className="rounded bg-surface-sunken px-2 py-0.5 text-xs font-semibold tabular-nums text-text-2">
                    {query.data?.total}
                  </span>
                </div>
                <ul className="m-0 mt-2 list-none divide-y divide-border p-0">
                  {query.data?.items.map((row) => (
                    <li key={row.id}>
                      <SignalLink row={row} language={i18n.resolvedLanguage ?? i18n.language} />
                    </li>
                  ))}
                </ul>
                {(query.data?.total ?? 0) > (query.data?.items.length ?? 0) && (
                  <Link
                    to={`/signals?status=${status}`}
                    className="mt-2 inline-flex min-h-11 items-center px-2 text-sm text-link hover:underline"
                  >
                    {t('work.openAll')}
                  </Link>
                )}
              </section>
            ))}
          </div>
        </section>

        <aside className="min-w-0 space-y-3" aria-labelledby="work-red-objects-title">
          <div>
            <h2 id="work-red-objects-title" className="text-lg font-semibold">
              {t('work.redObjectsTitle')}
            </h2>
            <p className="mt-1 text-xs leading-relaxed text-text-3">{t('work.redObjectsNote')}</p>
          </div>

          <div className="rounded border border-border bg-surface px-3">
            {dashboard.isError ? (
              <ErrorBlock error={dashboard.error} onRetry={() => void dashboard.refetch()} />
            ) : dashboard.isPending ? (
              <LoadingBlock label={t('work.loadingDashboard')} />
            ) : redObjects.length > 0 ? (
              <ul className="m-0 list-none divide-y divide-border p-0">
                {redObjects.map((object) => (
                  <li key={object.id}>
                    <Link
                      to={`/objects/${object.id}`}
                      className="flex min-h-11 items-center justify-between gap-3 py-2 text-sm text-text no-underline hover:text-accent-text focus-visible:ring-2 focus-visible:ring-focus"
                    >
                      <span className="min-w-0 truncate">{object.name}</span>
                      <IconChevronRight className="size-4 flex-none text-text-3" aria-hidden />
                    </Link>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="my-3 text-sm text-text-2">{t('work.noRedObjects')}</p>
            )}
          </div>

          <Link to="/objects" className="inline-flex min-h-11 items-center text-sm text-link hover:underline">
            {t('work.openObjects')}
          </Link>
        </aside>
      </div>
      <ReportCard />
    </div>
  );
}
