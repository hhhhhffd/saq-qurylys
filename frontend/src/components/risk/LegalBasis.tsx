import { useTranslation } from 'react-i18next';
import type { CheckStatus, LegalBasisStatus, LegalCheck, R1Detail } from '@/api/types';
import { Chip, type ChipTone } from '@/components/Chip';
import { useEnum } from '@/i18n/useEnum';

const BASIS_TONE: Record<LegalBasisStatus, ChipTone> = {
  confirmed: 'green',
  absent_established: 'red',
  unknown: 'yellow',
};
const CHECK_TONE: Record<CheckStatus | 'none', ChipTone> = {
  confirmed: 'green',
  checking: 'yellow',
  not_found: 'red',
  none: 'neutral',
};

interface Props {
  status: LegalBasisStatus;
  /** result of the check of each document type; omitted where the snapshot has none */
  checks?: R1Detail['checks'] | null;
}

/** Legal basis of attracting shareholders' money (SPEC 6.0): the verdict and the check of each document type. */
export function LegalBasis({ status, checks }: Props) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const rows: [keyof R1Detail['checks'], LegalCheck][] = checks
    ? [
        ['guarantee', checks.guarantee],
        ['dsu_permit', checks.dsu_permit],
      ]
    : [];

  return (
    <section className="mt-4" aria-labelledby="legal-basis-title">
      <div className="mb-2 flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <h4 id="legal-basis-title" className="m-0 font-heading text-2xs font-bold tracking-wider text-text-2 uppercase">
          {t('card.legalBasis.title')}
        </h4>
        <Chip tone={BASIS_TONE[status]}>{e('legal_basis_status', status)}</Chip>
      </div>
      {rows.length > 0 && (
        <dl className="m-0 flex flex-col gap-1.5 text-sm">
          {rows.map(([docType, result]) => (
            <div key={docType} className="flex items-center justify-between gap-3">
              <dt className="min-w-0 text-text-2">{e('doc_type', docType)}</dt>
              <dd className="m-0 flex-none">
                <Chip tone={CHECK_TONE[result]}>{e('check_status', result)}</Chip>
              </dd>
            </div>
          ))}
        </dl>
      )}
      <p className="mt-2 text-xs text-text-3">{t(`card.legalBasis.hint.${status}`)}</p>
    </section>
  );
}
