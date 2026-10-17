import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { FRAMES_PAGE_SIZE } from '@/api/hooks/vision';
import type { VisionFrame } from '@/api/types';
import { EmptyState, ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { Panel } from '@/components/Panel';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { formatTimestamp } from './constants';
import { FrameImage } from './FrameImage';

interface Props {
  frames: { items: VisionFrame[]; total: number } | undefined;
  error: unknown;
  onRetry: () => void;
  page: number;
  onPageChange: (page: number) => void;
  onOpen: (frameId: number) => void;
  /** frames with at least one finding get a mark */
  markedFrameIds: Set<number>;
  /** frames with a model finding still waiting for the specialist */
  pendingModelFrameIds: Set<number>;
}

export function FramesGallery({ frames, error, onRetry, page, onPageChange, onOpen, markedFrameIds, pendingModelFrameIds }: Props) {
  const { t } = useTranslation('vision');
  const pages = Math.max(1, Math.ceil((frames?.total ?? 0) / FRAMES_PAGE_SIZE));

  let body;
  if (frames === undefined) {
    body = error ? <ErrorBlock error={error} onRetry={onRetry} /> : <LoadingBlock />;
  } else if (frames.items.length === 0) {
    body = <EmptyState>{t('frames.empty')}</EmptyState>;
  } else {
    body = (
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-6">
        {frames.items.map((frame) => {
          const label = frame.timestamp_ms !== null ? formatTimestamp(frame.timestamp_ms) : t('frames.photo');
          return (
            <li key={frame.id}>
              <button
                type="button"
                data-testid="vision-frame"
                aria-label={t('frames.open', { label })}
                className={cn(
                  'group relative block w-full overflow-hidden rounded border border-border bg-surface-sunken text-left transition-shadow hover:border-border-strong hover:shadow-glow focus-visible:ring-1 focus-visible:ring-focus focus-visible:outline-none',
                  !frame.usable && 'opacity-60',
                )}
                onClick={() => onOpen(frame.id)}
              >
                <FrameImage frameId={frame.id} variant="preview" alt="" className="aspect-video w-full" imgClassName="object-cover" />
                <span className="absolute bottom-1 left-1 rounded-sm bg-scrim px-1 text-2xs text-text tabular-nums">{label}</span>
                {markedFrameIds.has(frame.id) && (
                  <span className="absolute top-1 right-1 rounded-sm bg-primary px-1 text-2xs text-primary-foreground">
                    {t('frames.marked')}
                  </span>
                )}
                {pendingModelFrameIds.has(frame.id) && (
                  <span className="absolute top-1 right-1 mt-5 rounded-sm border border-dashed border-text bg-scrim px-1 text-2xs text-text">
                    {t('frames.modelMarked')}
                  </span>
                )}
                {!frame.usable && (
                  <span className="absolute top-1 left-1 rounded-sm bg-scrim px-1 text-2xs text-text-2">{t('frames.unusable')}</span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <Panel
      title={t('frames.title')}
      actions={
        pages > 1 && (
          <div className="flex items-center gap-2 text-xs text-text-2">
            <Button variant="ghost" size="icon-sm" aria-label={t('frames.prev')} disabled={page === 0} onClick={() => onPageChange(page - 1)}>
              <IconChevronLeft />
            </Button>
            <span className="tabular-nums">{t('frames.page', { page: page + 1, pages })}</span>
            <Button variant="ghost" size="icon-sm" aria-label={t('frames.next')} disabled={page >= pages - 1} onClick={() => onPageChange(page + 1)}>
              <IconChevronRight />
            </Button>
          </div>
        )
      }
    >
      {body}
    </Panel>
  );
}
