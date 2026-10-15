import { useState, type CSSProperties } from 'react';
import { IconFileOff, IconFileTypePdf, IconPhoto } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useEvidenceContent } from '@/api/hooks/misc';
import type { EvidenceMeta } from '@/api/types';
import { openFile } from '@/api/client';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Spinner } from '@/components/ui/spinner';
import { useEnum } from '@/i18n/useEnum';
import { cn } from '@/lib/utils';

interface ImageProps {
  id: number;
  alt: string;
  /** thumbnail box size in px; images are fitted with object-fit: cover */
  size?: number;
  /** open a larger preview on click (default true) */
  zoomable?: boolean;
}

/** Evidence PNG/photo. Content is fetched with the Bearer token as a blob (SPEC §8). */
export function EvidenceImage({ id, alt, size = 72, zoomable = true }: ImageProps) {
  const { t } = useTranslation();
  const { data, isPending, isError } = useEvidenceContent(id);
  const [open, setOpen] = useState(false);
  const style: CSSProperties = { width: size, height: size };
  const thumbClass = 'inline-flex flex-none items-center justify-center overflow-hidden rounded bg-surface-sunken text-text-3';

  if (isPending) {
    return (
      <span className={thumbClass} style={style}>
        <Spinner role="presentation" aria-hidden className="size-3.5" />
      </span>
    );
  }
  if (isError) {
    return (
      <span className={thumbClass} style={style} title={t('states.loadError')}>
        <IconFileOff size={18} stroke={1.5} />
      </span>
    );
  }
  return (
    <>
      <button
        type="button"
        className={cn(
          thumbClass,
          'cursor-zoom-in border border-border p-0 transition-shadow hover:border-border-strong hover:shadow-glow focus-visible:ring-1 focus-visible:ring-focus focus-visible:outline-none',
        )}
        style={style}
        onClick={() => zoomable && setOpen(true)}
        aria-label={alt}
      >
        <img src={data.url} alt={alt} className="block size-full object-cover" loading="lazy" />
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-fit" aria-describedby={undefined}>
          <DialogHeader>
            <DialogTitle>{alt}</DialogTitle>
          </DialogHeader>
          <img src={data.url} alt={alt} className="block max-h-[75vh] max-w-[min(90vw,1100px)] rounded object-contain" />
        </DialogContent>
      </Dialog>
    </>
  );
}

interface ThumbsProps {
  evidence: EvidenceMeta[];
  size?: number;
}

/** Row of evidence previews: images inline, other kinds as download chips. */
export function EvidenceThumbs({ evidence, size = 72 }: ThumbsProps) {
  const e = useEnum();
  return (
    <div className="flex flex-wrap gap-2">
      {evidence.map((item) =>
        item.content_type.startsWith('image/') ? (
          <EvidenceImage key={item.id} id={item.id} alt={`${e('evidence_kind', item.kind)} #${item.id}`} size={size} />
        ) : (
          <button
            key={item.id}
            type="button"
            className="inline-flex items-center gap-1.5 rounded border border-border-strong bg-surface-raised px-2.5 py-1.5 text-sm text-text hover:bg-hover focus-visible:ring-1 focus-visible:ring-focus focus-visible:outline-none"
            onClick={() => void openFile(`/evidence/${item.id}/content`)}
          >
            {item.content_type === 'application/pdf' ? <IconFileTypePdf size={16} /> : <IconPhoto size={16} />}
            {e('evidence_kind', item.kind)}
          </button>
        ),
      )}
    </div>
  );
}
