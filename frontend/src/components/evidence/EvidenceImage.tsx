import { useState, type CSSProperties } from 'react';
import { Loader, Modal } from '@mantine/core';
import { IconFileOff, IconFileTypePdf, IconPhoto } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useEvidenceContent } from '@/api/hooks/misc';
import type { EvidenceMeta } from '@/api/types';
import { openFile } from '@/api/client';
import { useEnum } from '@/i18n/useEnum';
import classes from './Evidence.module.css';

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

  if (isPending) {
    return (
      <span className={classes.thumb} style={style}>
        <Loader size="xs" />
      </span>
    );
  }
  if (isError) {
    return (
      <span className={classes.thumb} style={style} title={t('states.loadError')}>
        <IconFileOff size={18} stroke={1.5} />
      </span>
    );
  }
  return (
    <>
      <button
        type="button"
        className={classes.thumbButton}
        style={style}
        onClick={() => zoomable && setOpen(true)}
        aria-label={alt}
      >
        <img src={data.url} alt={alt} className={classes.img} loading="lazy" />
      </button>
      <Modal opened={open} onClose={() => setOpen(false)} title={alt} size="auto" centered>
        <img src={data.url} alt={alt} className={classes.full} />
      </Modal>
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
    <div className={classes.row}>
      {evidence.map((item) =>
        item.content_type.startsWith('image/') ? (
          <EvidenceImage key={item.id} id={item.id} alt={`${e('evidence_kind', item.kind)} #${item.id}`} size={size} />
        ) : (
          <button
            key={item.id}
            type="button"
            className={classes.fileChip}
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
