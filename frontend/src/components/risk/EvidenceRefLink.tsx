import { Link } from 'react-router';
import { openFile } from '@/api/client';
import type { EvidenceRef } from '@/api/types';
import { useEnum } from '@/i18n/useEnum';
import { anchorId, isAnchorType } from './anchors';
import { cn } from '@/lib/utils';

interface Props {
  evidenceRef: EvidenceRef;
  /** false where the registry is out of reach (a receiving body sees no ads or objects) */
  linked?: boolean;
  /** false where the referenced document, complaint or inspection is not on the page */
  anchors?: boolean;
}

/** Chip that leads to the record a risk factor is based on. */
const refClass = 'inline-flex items-center rounded-sm border border-border-strong px-1.5 py-px text-2xs leading-snug whitespace-nowrap';
const interactiveClass = cn(refClass, 'cursor-pointer bg-transparent text-link no-underline transition-colors hover:bg-hover focus-visible:ring-1 focus-visible:ring-focus focus-visible:outline-none');

export function EvidenceRefLink({ evidenceRef, linked = true, anchors = true }: Props) {
  const e = useEnum();
  const label = `${e('entity_type', evidenceRef.type)} #${evidenceRef.id}`;

  if (linked && evidenceRef.type === 'ad_post') {
    const hit = evidenceRef.phrase_hit_id ? `&hit=${evidenceRef.phrase_hit_id}` : '';
    return (
      <Link className={interactiveClass} to={`/ads?ad=${evidenceRef.id}${hit}`}>
        {label}
      </Link>
    );
  }
  if (anchors && isAnchorType(evidenceRef.type)) {
    return (
      <a className={interactiveClass} href={`#${anchorId(evidenceRef.type, evidenceRef.id)}`}>
        {label}
      </a>
    );
  }
  if (linked && evidenceRef.type === 'evidence') {
    return (
      <button
        type="button"
        className={interactiveClass}
        onClick={() => void openFile(`/evidence/${evidenceRef.id}/content`)}
      >
        {label}
      </button>
    );
  }
  return <span className={cn(refClass, 'text-text-2')}>{label}</span>;
}
