import { useState } from 'react';
import { IconArrowLeft, IconCheck } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';
import { useMarkSessionReviewed, useUpdateVisionSession, useVisionConfig, useVisionFrames, useVisionSession } from '@/api/hooks/vision';
import type { VisionConfig, VisionFinding, VisionSessionDetail } from '@/api/types';
import { DemoBadge } from '@/components/DemoBadge';
import { ObjectSelect } from '@/components/ObjectSelect';
import { PageHeader } from '@/components/PageHeader';
import { Panel } from '@/components/Panel';
import { EmptyState, QueryBoundary } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { confirmAction } from '@/lib/confirm';
import { AssetsPanel } from './AssetsPanel';
import { FindingsPanels } from './FindingsPanels';
import { FrameViewer } from './FrameViewer';
import { FramesGallery } from './FramesGallery';
import { SessionStatusChips } from './SessionStatusChips';
import { UploadPanel } from './UploadPanel';

function ObjectField({ session }: { session: VisionSessionDetail }) {
  const { t } = useTranslation('vision');
  const { t: tc } = useTranslation();
  const update = useUpdateVisionSession(session.id);
  const [opened, setOpened] = useState(false);
  const [draft, setDraft] = useState<number | null>(null);
  const current = session.object?.id ?? null;

  return (
    <div className="flex flex-wrap items-center gap-2">
      {session.object ? (
        <Link to={`/objects/${session.object.id}`} className="font-semibold [overflow-wrap:anywhere]">
          {session.object.code} · {session.object.name}
        </Link>
      ) : (
        <span className="text-text-3">{t('unlinked')}</span>
      )}
      <Popover
        open={opened}
        onOpenChange={(next) => {
          if (next) setDraft(current);
          setOpened(next);
        }}
      >
        <PopoverTrigger asChild>
          <Button size="xs" variant="secondary">
            {session.object ? t('header.change') : t('header.attach')}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-80 gap-3 p-3">
          <ObjectSelect label={t('new.object')} placeholder={t('new.objectPlaceholder')} value={draft} onChange={setDraft} />
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="sm" onClick={() => setOpened(false)}>
              {tc('cancel')}
            </Button>
            <Button
              size="sm"
              disabled={draft === current}
              loading={update.isPending}
              onClick={() => update.mutate({ object_id: draft }, { onSuccess: () => setOpened(false) })}
            >
              {tc('save')}
            </Button>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}

function SessionView({ session, config }: { session: VisionSessionDetail; config: VisionConfig }) {
  const { t } = useTranslation('vision');
  const e = useEnum();
  const f = useFormat();
  const markReviewed = useMarkSessionReviewed(session.id);
  const [page, setPage] = useState(0);
  const [viewer, setViewer] = useState<{ frameId: number; findingId: number | null } | null>(null);
  const frames = useVisionFrames(session.id, page, session.processing);
  const markedFrameIds = new Set(session.findings.flatMap((finding) => (finding.frame_id !== null ? [finding.frame_id] : [])));

  const showFinding = (finding: VisionFinding) => {
    if (finding.frame_id !== null) setViewer({ frameId: finding.frame_id, findingId: finding.id });
  };
  const askReviewed = () =>
    confirmAction({
      title: t('header.reviewTitle'),
      message: t('header.reviewMessage'),
      confirmLabel: t('header.review'),
      onConfirm: () => markReviewed.mutate(),
    });

  const meta: [string, React.ReactNode][] = [
    [t('header.source'), e('vision_source', session.source)],
    [t('header.capturedAt'), <span key="c" className="tabular-nums">{f.dateTime(session.captured_at)}</span>],
    [t('header.createdAt'), <span key="n" className="tabular-nums">{f.dateTime(session.created_at)} · {session.created_by_name ?? '—'}</span>],
  ];

  return (
    <>
      <PageHeader
        title={
          <span className="inline-flex flex-wrap items-center gap-x-3 gap-y-1">
            {t('session.title', { id: session.id })}
            {session.is_demo && <DemoBadge />}
          </span>
        }
        subtitle={<SessionStatusChips session={session} />}
        actions={
          <>
            <Button variant="secondary" asChild>
              <Link to="/vision">
                <IconArrowLeft />
                {t('session.back')}
              </Link>
            </Button>
            {session.status === 'open' && (
              <Button loading={markReviewed.isPending} onClick={askReviewed}>
                <IconCheck />
                {t('header.review')}
              </Button>
            )}
          </>
        }
      />
      <div className="flex flex-col gap-4">
        <Panel title={t('header.title')}>
          <dl className="m-0 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
            <dt className="text-text-3">{t('header.object')}</dt>
            <dd className="m-0">
              <ObjectField session={session} />
            </dd>
            {meta.map(([label, value]) => (
              <div key={label} className="contents">
                <dt className="text-text-3">{label}</dt>
                <dd className="m-0">{value}</dd>
              </div>
            ))}
            {session.status === 'reviewed' && (
              <>
                <dt className="text-text-3">{t('header.reviewedBy')}</dt>
                <dd className="m-0 tabular-nums">
                  {f.dateTime(session.reviewed_at)} · {session.reviewed_by_name ?? '—'}
                </dd>
              </>
            )}
            {session.note && (
              <>
                <dt className="text-text-3">{t('header.note')}</dt>
                <dd className="m-0 [overflow-wrap:anywhere]">{session.note}</dd>
              </>
            )}
          </dl>
        </Panel>

        <p role="note" className="m-0 rounded border border-border-strong bg-surface-sunken p-3 text-sm text-text-2">
          {config.ocr_enabled ? t('banner.detectorOff') : t('banner.detectorAndOcrOff')}
        </p>

        <UploadPanel sessionId={session.id} config={config} />
        <AssetsPanel assets={session.assets} />
        <FramesGallery
          frames={frames.data}
          error={frames.error}
          onRetry={() => void frames.refetch()}
          page={page}
          onPageChange={setPage}
          onOpen={(frameId) => setViewer({ frameId, findingId: null })}
          markedFrameIds={markedFrameIds}
        />
        <FindingsPanels session={session} config={config} onShow={showFinding} />
      </div>
      {viewer && (
        <FrameViewer
          session={session}
          frameId={viewer.frameId}
          frames={frames.data?.items ?? []}
          focusFindingId={viewer.findingId}
          onFrameChange={(frameId) => setViewer({ frameId, findingId: null })}
          onClose={() => setViewer(null)}
        />
      )}
    </>
  );
}

export function SessionPage() {
  const { t } = useTranslation('vision');
  const params = useParams();
  const id = Number(params.id);
  const config = useVisionConfig();
  const session = useVisionSession(Number.isInteger(id) && id > 0 ? id : 0);

  if (!Number.isInteger(id) || id <= 0) return <EmptyState>{t('session.notFound')}</EmptyState>;
  return (
    <QueryBoundary query={session}>
      {(data) => (config.data ? <SessionView session={data} config={config.data} /> : null)}
    </QueryBoundary>
  );
}
