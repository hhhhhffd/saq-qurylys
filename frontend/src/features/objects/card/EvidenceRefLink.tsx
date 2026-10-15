import { Link } from 'react-router';
import { openFile } from '@/api/client';
import type { EvidenceRef } from '@/api/types';
import { useEnum } from '@/i18n/useEnum';
import { anchorId, isAnchorType } from './anchors';
import classes from './EvidenceRefLink.module.css';

/** Chip that leads to the record a risk factor is based on. */
export function EvidenceRefLink({ evidenceRef }: { evidenceRef: EvidenceRef }) {
  const e = useEnum();
  const label = `${e('entity_type', evidenceRef.type)} #${evidenceRef.id}`;

  if (evidenceRef.type === 'ad_post') {
    return (
      <Link className={classes.ref} to={`/ads?ad=${evidenceRef.id}`}>
        {label}
      </Link>
    );
  }
  if (isAnchorType(evidenceRef.type)) {
    return (
      <a className={classes.ref} href={`#${anchorId(evidenceRef.type, evidenceRef.id)}`}>
        {label}
      </a>
    );
  }
  if (evidenceRef.type === 'evidence') {
    return (
      <button type="button" className={classes.ref} onClick={() => void openFile(`/evidence/${evidenceRef.id}/content`)}>
        {label}
      </button>
    );
  }
  return <span className={classes.ref}>{label}</span>;
}
