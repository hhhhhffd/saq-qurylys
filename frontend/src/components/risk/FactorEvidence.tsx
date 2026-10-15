import { useTranslation } from 'react-i18next';
import type { EvidenceRef } from '@/api/types';
import { EvidenceRefLink } from './EvidenceRefLink';
import classes from './FactorEvidence.module.css';

interface Props {
  evidence: EvidenceRef[];
  linked?: boolean;
  anchors?: boolean;
}

/** Basis of a risk factor: quoted phrases (R2) with a link to their publication, then the other records. */
export function FactorEvidence({ evidence, linked, anchors }: Props) {
  const { t } = useTranslation('objects');
  if (evidence.length === 0) return null;
  const quoted = evidence.filter((ref) => ref.fragment);
  const plain = evidence.filter((ref) => !ref.fragment);

  return (
    <div className={classes.root}>
      {quoted.length > 0 && (
        <ul className={classes.quotes} aria-label={t('card.breakdown.fragments')}>
          {quoted.map((ref) => (
            <li key={`${ref.type}-${ref.id}-${ref.phrase_hit_id ?? ref.fragment}`}>
              <span className={classes.fragment}>«{ref.fragment}»</span>
              <EvidenceRefLink evidenceRef={ref} linked={linked} anchors={anchors} />
            </li>
          ))}
        </ul>
      )}
      {plain.length > 0 && (
        <div className={classes.refs}>
          <span className={classes.label}>{t('card.breakdown.evidence')}</span>
          {plain.map((ref) => (
            <EvidenceRefLink key={`${ref.type}-${ref.id}`} evidenceRef={ref} linked={linked} anchors={anchors} />
          ))}
        </div>
      )}
    </div>
  );
}
