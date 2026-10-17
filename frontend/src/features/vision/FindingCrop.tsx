import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useFrameImage } from '@/api/hooks/vision';
import type { VisionFinding } from '@/api/types';
import { FrameImage } from './FrameImage';

const MAX_W = 128;
const MAX_H = 96;

/** The marked area cut out of the frame preview with CSS only; without a box, the whole frame as a small thumbnail. */
export function FindingCrop({ finding }: { finding: VisionFinding }) {
  const { t } = useTranslation('vision');
  const frameId = finding.frame_id;
  const { data } = useFrameImage(frameId, 'preview');
  const [natural, setNatural] = useState<{ width: number; height: number } | null>(null);
  const bbox = finding.bbox;
  if (frameId === null) return null;

  if (!bbox) {
    return <FrameImage frameId={frameId} variant="preview" alt={t('finding.cropAlt')} className="h-16 w-24 rounded border border-border" imgClassName="object-cover" />;
  }

  // The box is a fraction of the frame, so its pixel shape needs the size of the image; it is read once the image loads.
  const ratio = natural ? (bbox.w * natural.width) / (bbox.h * natural.height) : 4 / 3;
  const width = Math.min(MAX_W, MAX_H * ratio);
  return (
    <span
      className="relative block flex-none overflow-hidden rounded border border-border bg-surface-sunken"
      style={{ width, aspectRatio: ratio }}
      role="img"
      aria-label={t('finding.cropAlt')}
    >
      {data && (
        <img
          src={data.url}
          alt=""
          draggable={false}
          className="absolute max-w-none"
          style={{ width: `${100 / bbox.w}%`, left: `${(-bbox.x / bbox.w) * 100}%`, top: `${(-bbox.y / bbox.h) * 100}%` }}
          onLoad={(event) => setNatural({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })}
        />
      )}
    </span>
  );
}
