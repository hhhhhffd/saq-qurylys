import { useState } from 'react';
import { IconAlertTriangle, IconRefresh } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useRegistrySyncStatus, useStartRegistrySync } from '@/api/hooks/reference';
import type { RegistrySyncResult, RegistrySyncStatus } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Chip } from '@/components/Chip';
import { KeyValue } from '@/components/KeyValue';
import { Panel } from '@/components/Panel';
import { QueryBoundary } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { useFormat } from '@/i18n/useFormat';
import { SectionHeader } from './SectionHeader';

const STAT_KEYS = [
  'fetched',
  'objects_created',
  'documents_created',
  'documents_updated',
  'documents_unconfirmed',
  'skipped',
] as const;

function LastSync({ result }: { result: RegistrySyncResult | null }) {
  const { t } = useTranslation('admin');
  const { dateTime } = useFormat();
  if (!result) return <p className="text-text-2">{t('registry.last.none')}</p>;

  return (
    <>
      <div className="flex flex-wrap items-center gap-3">
        <Chip tone={result.ok ? 'green' : 'red'}>{result.ok ? t('registry.last.ok') : t('registry.last.failed')}</Chip>
        <span className="text-text-2 tabular-nums">
          {t('registry.last.startedAt')}: {dateTime(result.started_at)} · {t('registry.last.finishedAt')}:{' '}
          {dateTime(result.finished_at)}
        </span>
      </div>
      <KeyValue
        columns={3}
        items={STAT_KEYS.map((key) => ({
          label: t(`registry.last.stats.${key}`),
          value: <span className="tabular-nums">{result[key]}</span>,
        }))}
      />
      {result.errors.length > 0 && (
        <div>
          <h4 className="mb-1 text-xs font-bold tracking-wider uppercase">{t('registry.last.errors')}</h4>
          <ul className="list-disc pl-5 text-sm text-zone-red-ink">
            {result.errors.map((error, index) => (
              <li key={index}>{error}</li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

function SyncPanel({
  status,
  baseline,
  onStart,
}: {
  status: RegistrySyncStatus;
  baseline: string | null | undefined;
  onStart: () => void;
}) {
  const { t } = useTranslation('admin');
  const { user } = useAuth();
  const start = useStartRegistrySync();
  const finishedAt = status.last_sync?.finished_at ?? null;
  // A run was started and the status has not changed yet: its result is still to come.
  const running = baseline !== undefined && finishedAt === baseline;
  const globalAdmin = user?.territory_id === null;

  return (
    <div className="flex flex-col gap-7">
      <div role="note" className="flex items-start gap-2.5 rounded border border-zone-yellow/40 bg-zone-yellow-bg p-3 text-sm text-zone-yellow-ink">
        <IconAlertTriangle size={18} aria-hidden className="mt-0.5 flex-none" />
        <div>
          <p className="font-heading text-xs font-bold tracking-wider uppercase">{t('registry.warningTitle')}</p>
          <p className="mt-0.5">{t('registry.warning')}</p>
        </div>
      </div>
      <Panel
        title={t('registry.last.title')}
        actions={
          <Button
            loading={start.isPending}
            disabled={running || !globalAdmin}
            onClick={() => start.mutate(undefined, { onSuccess: onStart })}
          >
            {running ? <Spinner /> : <IconRefresh />}
            {running ? t('registry.running') : t('registry.start')}
          </Button>
        }
      >
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-text-2">{t('registry.scheduled')}:</span>
            <Chip tone={status.scheduled_enabled ? 'green' : 'neutral'}>
              {status.scheduled_enabled ? t('registry.scheduledOn') : t('registry.scheduledOff')}
            </Chip>
            {!globalAdmin && <span className="text-text-2">{t('registry.globalOnly')}</span>}
          </div>
          <LastSync result={status.last_sync} />
        </div>
      </Panel>
    </div>
  );
}

export function RegistrySection() {
  const { t } = useTranslation('admin');
  // `undefined`: nothing started in this session; otherwise the `finished_at` of the last run when it was started.
  const [baseline, setBaseline] = useState<string | null | undefined>(undefined);
  const query = useRegistrySyncStatus(baseline !== undefined);

  return (
    <section>
      <SectionHeader title={t('registry.title')} description={t('registry.description')} />
      <QueryBoundary query={query}>
        {(status) => (
          <SyncPanel
            status={status}
            baseline={baseline}
            onStart={() => setBaseline(status.last_sync?.finished_at ?? null)}
          />
        )}
      </QueryBoundary>
    </section>
  );
}
