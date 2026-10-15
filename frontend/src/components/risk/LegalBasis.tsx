import { useTranslation } from 'react-i18next';
import type { CheckStatus, LegalBasisStatus, LegalCheck, R1Detail } from '@/api/types';
import { Chip, type ChipTone } from '@/components/Chip';
import { useEnum } from '@/i18n/useEnum';
import classes from './LegalBasis.module.css';

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
    <section className={classes.root} aria-labelledby="legal-basis-title">
      <div className={classes.head}>
        <h4 id="legal-basis-title" className={classes.title}>
          {t('card.legalBasis.title')}
        </h4>
        <Chip tone={BASIS_TONE[status]}>{e('legal_basis_status', status)}</Chip>
      </div>
      {rows.length > 0 && (
        <dl className={classes.checks}>
          {rows.map(([docType, result]) => (
            <div key={docType}>
              <dt>{e('doc_type', docType)}</dt>
              <dd>
                <Chip tone={CHECK_TONE[result]}>{e('check_status', result)}</Chip>
              </dd>
            </div>
          ))}
        </dl>
      )}
      <p className={classes.hint}>{t(`card.legalBasis.hint.${status}`)}</p>
    </section>
  );
}
