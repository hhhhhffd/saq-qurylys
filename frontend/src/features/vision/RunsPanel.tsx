import { IconRefresh } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useReanalyzeSession } from '@/api/hooks/vision';
import type { VisionConfig, VisionRun, VisionSessionDetail } from '@/api/types';
import { Chip } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { Button } from '@/components/ui/button';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { confirmAction } from '@/lib/confirm';
import { DETECTED_CATEGORIES, RUN_STATUS_TONE } from './constants';

function RunRow({ run }: { run: VisionRun }) {
  const { t } = useTranslation('vision');
  const { t: tc } = useTranslation();
  const e = useEnum();
  const f = useFormat();
  const percent = run.frames_total > 0 ? Math.min(100, Math.round((run.frames_done / run.frames_total) * 100)) : 0;
  const time = run.finished_at
    ? t('runs.finished', { time: f.dateTime(run.finished_at) })
    : run.started_at
      ? t('runs.started', { time: f.dateTime(run.started_at) })
      : null;

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded border border-border p-2 text-sm" data-testid="vision-run">
      <strong>{t('runs.run', { id: run.id })}</strong>
      <Chip tone={RUN_STATUS_TONE[run.status]}>{e('vision_run_status', run.status)}</Chip>
      <span
        className="h-1.5 w-28 overflow-hidden rounded-full bg-surface-sunken"
        role="progressbar"
        aria-label={t('runs.run', { id: run.id })}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <span className="block h-full rounded-full bg-primary" style={{ width: `${percent}%` }} />
      </span>
      <span className="text-xs text-text-2 tabular-nums">{t('runs.progress', { done: run.frames_done, total: run.frames_total })}</span>
      <span className="text-xs text-text-3 [overflow-wrap:anywhere]">{run.model_version}</span>
      {time && <span className="text-xs text-text-3 tabular-nums">{time}</span>}
      {run.status === 'failed' && (
        <span className="basis-full text-xs text-zone-red-ink">
          {run.error_code ? tc(`errors.${run.error_code}`, { defaultValue: t('runs.errorFallback') }) : t('runs.errorFallback')}
        </span>
      )}
    </li>
  );
}

/** Runs of the neural detector over the session and what the last finished one found. Never says "none / violation". */
export function RunsPanel({ session, config }: { session: VisionSessionDetail; config: VisionConfig }) {
  const { t } = useTranslation('vision');
  const e = useEnum();
  const reanalyze = useReanalyzeSession(session.id);
  const enabled = config.detector_mode !== 'disabled';
  const active = session.runs.some((run) => run.status === 'queued' || run.status === 'running');
  // newest first, whatever order the server returns
  const runs = [...session.runs].sort((a, b) => b.id - a.id);
  const latest = runs.find((run) => run.status === 'completed');

  const ask = () =>
    confirmAction({
      title: t('runs.reanalyzeTitle'),
      message: t('runs.reanalyzeMessage'),
      confirmLabel: t('runs.reanalyze'),
      onConfirm: () => reanalyze.mutate(),
    });

  return (
    <Panel
      title={t('runs.title')}
      actions={
        enabled && (
          <Button size="sm" variant="secondary" disabled={active} loading={reanalyze.isPending} onClick={ask}>
            <IconRefresh />
            {t('runs.reanalyze')}
          </Button>
        )
      }
    >
      <div className="flex flex-col gap-3">
        {runs.length === 0 ? (
          <p className="m-0 text-text-3">{t('runs.empty')}</p>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-2 p-0" aria-label={t('runs.list')}>
            {runs.map((run) => (
              <RunRow key={run.id} run={run} />
            ))}
          </ul>
        )}
        {latest && (
          <section aria-label={t('runs.summaryTitle', { id: latest.id })}>
            <h4 className="m-0 mb-1 text-2xs font-bold tracking-wider text-text-3 uppercase">{t('runs.summaryTitle', { id: latest.id })}</h4>
            <ul className="m-0 grid list-none gap-x-6 gap-y-1 p-0 text-sm sm:grid-cols-2">
              {DETECTED_CATEGORIES.map((category) => {
                const count = latest.summary[category] ?? 0;
                return (
                  <li key={category} className="flex flex-wrap gap-x-2">
                    <strong>{e('vision_category', category)}</strong>
                    <span className={count > 0 ? 'text-text' : 'text-text-3'}>
                      {count > 0 ? t('runs.detected', { count }) : t('runs.notDetected')}
                    </span>
                  </li>
                );
              })}
            </ul>
          </section>
        )}
      </div>
    </Panel>
  );
}
