import { useTranslation } from 'react-i18next';
import type { EvidenceRef } from '@/api/types';
import { EvidenceRefLink } from './EvidenceRefLink';

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
    <div className="mt-2 flex flex-col gap-2">
      {quoted.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-1.5 p-0" aria-label={t('card.breakdown.fragments')}>
          {quoted.map((ref) => (
            <li
              key={`${ref.type}-${ref.id}-${ref.phrase_hit_id ?? ref.fragment}`}
              className="flex flex-wrap items-baseline gap-x-2 gap-y-1 border-l-2 border-zone-yellow pl-2.5"
            >
              <span className="text-sm text-text italic [overflow-wrap:anywhere]">«{ref.fragment}»</span>
              <EvidenceRefLink evidenceRef={ref} linked={linked} anchors={anchors} />
            </li>
          ))}
        </ul>
      )}
      {plain.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
          <span className="text-xs text-text-3">{t('card.breakdown.evidence')}</span>
          {plain.map((ref) => (
            <EvidenceRefLink key={`${ref.type}-${ref.id}`} evidenceRef={ref} linked={linked} anchors={anchors} />
          ))}
        </div>
      )}
    </div>
  );
}
