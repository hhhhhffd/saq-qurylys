import { useTranslation } from 'react-i18next';
import type { SignalSections } from '@/api/types';
import { Panel } from '@/components/Panel';
import { FactorDetail } from '@/components/risk/FactorDetail';
import { FactorEvidence } from '@/components/risk/FactorEvidence';
import { LegalBasis } from '@/components/risk/LegalBasis';
import { NeedsCheckList } from '@/components/risk/NeedsCheckList';
import { useEnum } from '@/i18n/useEnum';
import classes from './Sections.module.css';

function signedWeight(weight: number): string {
  if (weight > 0) return `+${weight}`;
  return weight < 0 ? `−${Math.abs(weight)}` : '0';
}

interface Props {
  sections: Pick<SignalSections, 'risk_factors' | 'legal_basis_status' | 'needs_check'>;
  /** recipients cannot open the ads registry */
  linked: boolean;
}

export function RiskFactorsSection({ sections, linked }: Props) {
  const { t } = useTranslation('signals');
  const e = useEnum();
  const { risk_factors: items, legal_basis_status: basis, needs_check: needsCheck } = sections;
  return (
    <Panel title={t('sections.risk_factors')}>
      {items.length === 0 ? (
        <p className={classes.inlineEmpty}>{t('sections.empty')}</p>
      ) : (
        <ul className={classes.factors}>
          {items.map((item) => (
            <li key={item.code} className={classes.factor}>
              <span className={classes.factorName}>
                <span className={classes.factorLabel}>{item.label}</span>
                {e('risk_factor', item.code)}
              </span>
              <span className={classes.weight}>{signedWeight(item.weight)}</span>
              <div className={classes.factorDetail}>
                <FactorEvidence evidence={item.evidence} linked={linked} anchors={false} />
                <details className={classes.factorMore}>
                  <summary>{t('riskFactors.details')}</summary>
                  <FactorDetail detail={item.detail} />
                </details>
              </div>
            </li>
          ))}
        </ul>
      )}
      {basis && <LegalBasis status={basis} />}
      <NeedsCheckList items={needsCheck} linked={linked} anchors={false} />
    </Panel>
  );
}
