import { useTranslation } from 'react-i18next';
import type { SignalSections } from '@/api/types';
import { Panel } from '@/components/Panel';
import { FactorDetail } from '@/components/risk/FactorDetail';
import { FactorEvidence } from '@/components/risk/FactorEvidence';
import { LegalBasis } from '@/components/risk/LegalBasis';
import { NeedsCheckList } from '@/components/risk/NeedsCheckList';
import { useEnum } from '@/i18n/useEnum';

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
        <p className="text-text-3">{t('sections.empty')}</p>
      ) : (
        <ul className="m-0 flex list-none flex-col p-0">
          {items.map((item) => (
            <li
              key={item.code}
              className="grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-4 gap-y-1 border-b border-border py-2.5 first:pt-0 last:border-b-0 last:pb-0"
            >
              <span className="font-semibold">
                <span className="mr-2 inline-block min-w-7 rounded-sm bg-primary px-1.5 text-center text-xs font-bold text-primary-foreground">
                  {item.label}
                </span>
                {e('risk_factor', item.code)}
              </span>
              <span className="font-semibold tabular-nums">{signedWeight(item.weight)}</span>
              <div className="col-span-full">
                <FactorEvidence evidence={item.evidence} linked={linked} anchors={false} />
                <details className="mt-2 text-xs">
                  <summary className="cursor-pointer text-text-2 hover:text-text">{t('riskFactors.details')}</summary>
                  <div className="mt-2">
                    <FactorDetail detail={item.detail} />
                  </div>
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
