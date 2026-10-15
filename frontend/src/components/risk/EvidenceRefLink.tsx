import { Link } from 'react-router';
import { openFile } from '@/api/client';
import type { EvidenceRef } from '@/api/types';
import { useEnum } from '@/i18n/useEnum';
import { anchorId, isAnchorType } from './anchors';
import classes from './EvidenceRefLink.module.css';

interface Props {
  evidenceRef: EvidenceRef;
  /** false where the registry is out of reach (a receiving body sees no ads or objects) */
  linked?: boolean;
  /** false where the referenced document, complaint or inspection is not on the page */
  anchors?: boolean;
}

/** Chip that leads to the record a risk factor is based on. */
export function EvidenceRefLink({ evidenceRef, linked = true, anchors = true }: Props) {
  const e = useEnum();
  const label = `${e('entity_type', evidenceRef.type)} #${evidenceRef.id}`;

  if (linked && evidenceRef.type === 'ad_post') {
    const hit = evidenceRef.phrase_hit_id ? `&hit=${evidenceRef.phrase_hit_id}` : '';
    return (
      <Link className={classes.ref} to={`/ads?ad=${evidenceRef.id}${hit}`}>
        {label}
      </Link>
    );
  }
  if (anchors && isAnchorType(evidenceRef.type)) {
    return (
      <a className={classes.ref} href={`#${anchorId(evidenceRef.type, evidenceRef.id)}`}>
        {label}
      </a>
    );
  }
  if (linked && evidenceRef.type === 'evidence') {
    return (
      <button
        type="button"
        className={classes.ref}
        onClick={() => void openFile(`/evidence/${evidenceRef.id}/content`)}
      >
        {label}
      </button>
    );
  }
  return <span className={classes.ref}>{label}</span>;
}
