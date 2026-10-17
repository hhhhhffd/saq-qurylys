import { useRef, useState, type PointerEvent } from 'react';
import { IconChevronLeft, IconChevronRight, IconFocus2, IconX } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useCreateFinding } from '@/api/hooks/vision';
import type { FindingCategory, FindingStatus, VisionBbox, VisionFrame, VisionSessionDetail } from '@/api/types';
import { SelectInput } from '@/components/form/SelectInput';
import { TextArea } from '@/components/form/TextArea';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useEnum, useEnumOptions } from '@/i18n/useEnum';
import { cn } from '@/lib/utils';
import { CATEGORIES, FINDING_STATUSES, formatTimestamp, isCategory, isFindingStatus } from './constants';
import { FrameImage } from './FrameImage';

interface Props {
  session: VisionSessionDetail;
  frameId: number;
  /** frames of the page on screen: the previous/next buttons walk through them */
  frames: VisionFrame[];
  focusFindingId: number | null;
  onFrameChange: (frameId: number) => void;
  onClose: () => void;
}

const MIN_SIDE = 0.01;
const clamp = (value: number) => Math.min(1, Math.max(0, value));

/** The ORIGINAL frame with the boxes of its findings; the draw mode marks a new area as fractions of the image. */
export function FrameViewer({ session, frameId, frames, focusFindingId, onFrameChange, onClose }: Props) {
  const { t } = useTranslation('vision');
  const { t: tc } = useTranslation();
  const e = useEnum();
  const options = useEnumOptions();
  const createFinding = useCreateFinding(session.id);
  const overlayRef = useRef<HTMLDivElement>(null);
  const [drawing, setDrawing] = useState(false);
  // the boxes are fractions of the rendered image, so nothing can be drawn before it has its size
  const [loadedFrameId, setLoadedFrameId] = useState<number | null>(null);
  const ready = loadedFrameId === frameId;
  const [anchor, setAnchor] = useState<{ x: number; y: number } | null>(null);
  const [draft, setDraft] = useState<VisionBbox | null>(null);
  const [category, setCategory] = useState<FindingCategory>('outdoor_ad');
  const [status, setStatus] = useState<FindingStatus>('observed');
  const [note, setNote] = useState('');

  const index = frames.findIndex((frame) => frame.id === frameId);
  const frame = index >= 0 ? frames[index] : null;
  // a frame outside the gallery page on screen (opened from a finding) has no metadata here: name it by its number
  const label = !frame ? t('viewer.frameNumber', { id: frameId }) : frame.timestamp_ms != null ? formatTimestamp(frame.timestamp_ms) : t('frames.photo');
  const findings = session.findings.filter((finding) => finding.frame_id === frameId && finding.bbox);

  const reset = () => {
    setAnchor(null);
    setDraft(null);
    setNote('');
  };
  const move = (delta: number) => {
    const target = frames[index + delta];
    if (target) {
      reset();
      onFrameChange(target.id);
    }
  };

  const point = (event: PointerEvent) => {
    const rect = overlayRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || rect.height === 0) return null;
    return { x: clamp((event.clientX - rect.left) / rect.width), y: clamp((event.clientY - rect.top) / rect.height) };
  };
  const rectBetween = (from: { x: number; y: number }, to: { x: number; y: number }): VisionBbox => ({
    x: Math.min(from.x, to.x),
    y: Math.min(from.y, to.y),
    w: Math.abs(to.x - from.x),
    h: Math.abs(to.y - from.y),
  });

  const onPointerDown = (event: PointerEvent) => {
    const start = point(event);
    if (!ready || !drawing || !start) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setAnchor(start);
    setDraft(null);
  };
  const onPointerMove = (event: PointerEvent) => {
    const current = point(event);
    if (ready && anchor && current) setDraft(rectBetween(anchor, current));
  };
  const onPointerUp = (event: PointerEvent) => {
    const end = point(event);
    if (ready && anchor && end) {
      const box = rectBetween(anchor, end);
      setDraft(box.w >= MIN_SIDE && box.h >= MIN_SIDE ? box : null);
    }
    setAnchor(null);
  };

  const save = () => {
    if (!draft) return;
    createFinding.mutate(
      { frame_id: frameId, bbox: draft, category, status, note: note.trim() || null },
      {
        onSuccess: () => {
          reset();
          setDrawing(false);
        },
      },
    );
  };

  const box = (bbox: VisionBbox) => ({
    left: `${bbox.x * 100}%`,
    top: `${bbox.y * 100}%`,
    width: `${bbox.w * 100}%`,
    height: `${bbox.h * 100}%`,
  });

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-5xl" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{t('viewer.title', { label })}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" size="sm" aria-label={t('viewer.prev')} disabled={index <= 0} onClick={() => move(-1)}>
            <IconChevronLeft />
          </Button>
          <Button variant="secondary" size="sm" aria-label={t('viewer.next')} disabled={index < 0 || index >= frames.length - 1} onClick={() => move(1)}>
            <IconChevronRight />
          </Button>
          <Button
            variant={drawing ? 'default' : 'secondary'}
            size="sm"
            aria-pressed={drawing}
            disabled={!ready}
            onClick={() => {
              setDrawing(!drawing);
              reset();
            }}
          >
            <IconFocus2 />
            {t('viewer.draw')}
          </Button>
          <span className="text-xs text-text-3">{drawing ? t('viewer.drawHint') : t('viewer.original')}</span>
        </div>
        <div className="flex max-h-[62vh] justify-center overflow-auto rounded bg-surface-sunken">
          {/* the wrapper shrink-wraps the image (block, no object-fit), so the overlay covers exactly the rendered pixels */}
          <div className={cn('relative inline-block max-w-full self-start', !ready && 'min-h-24 min-w-24')} data-testid="vision-frame-canvas">
            <FrameImage
              frameId={frameId}
              variant="original"
              alt={t('viewer.imageAlt', { label })}
              className="h-auto max-h-[60vh] w-auto max-w-full"
              onLoad={() => setLoadedFrameId(frameId)}
            />
            <div
              ref={overlayRef}
              className={cn('absolute inset-0 touch-none select-none', drawing && ready && 'cursor-crosshair')}
              onPointerDown={onPointerDown}
              onPointerMove={onPointerMove}
              onPointerUp={onPointerUp}
              data-testid="vision-frame-overlay"
            >
              {findings.map((finding) =>
                finding.bbox ? (
                  <span
                    key={finding.id}
                    className={cn(
                      'pointer-events-none absolute border-2 border-accent-text',
                      finding.origin === 'model' && 'border-dashed',
                      finding.id === focusFindingId && 'shadow-glow ring-2 ring-text',
                    )}
                    style={box(finding.bbox)}
                    data-origin={finding.origin}
                  >
                    <span className="absolute -top-px left-0 -translate-y-full bg-primary px-1 text-2xs whitespace-nowrap text-primary-foreground">
                      {finding.origin === 'model' && finding.confidence !== null
                        ? t('viewer.modelBox', { category: e('vision_category', finding.category) })
                        : e('vision_category', finding.category)}
                    </span>
                  </span>
                ) : null,
              )}
              {draft && <span className="pointer-events-none absolute border-2 border-dashed border-text bg-text/10" style={box(draft)} />}
            </div>
          </div>
        </div>
        {draft && (
          <div className="flex flex-col gap-3 rounded border border-border p-3" role="group" aria-label={t('viewer.newFinding')}>
            <div className="grid gap-3 sm:grid-cols-2">
              <SelectInput
                label={t('finding.category')}
                data={options('vision_category', CATEGORIES)}
                value={category}
                onChange={(value) => isCategory(value) && setCategory(value)}
              />
              <SelectInput
                label={t('finding.status')}
                data={options('vision_finding_status', FINDING_STATUSES)}
                value={status}
                onChange={(value) => isFindingStatus(value) && setStatus(value)}
              />
            </div>
            <TextArea label={t('finding.note')} minRows={2} maxRows={5} value={note} onChange={(event) => setNote(event.target.value)} />
            <div className="flex justify-end gap-2">
              <Button variant="secondary" onClick={reset}>
                <IconX />
                {tc('cancel')}
              </Button>
              <Button loading={createFinding.isPending} onClick={save}>
                {t('viewer.saveFinding')}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
