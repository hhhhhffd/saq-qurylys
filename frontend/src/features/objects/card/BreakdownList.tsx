import { IconCheck, IconChevronRight, IconMinus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { readBreakdown, type RiskScore } from '@/api/types';
import { Chip } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { FactorDetail } from '@/components/risk/FactorDetail';
import { FactorEvidence } from '@/components/risk/FactorEvidence';
import { useEnum } from '@/i18n/useEnum';
import { cn } from '@/lib/utils';
import { formatSigned } from './formatSigned';

export function BreakdownList({ score }: { score: RiskScore | null }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const factors = readBreakdown(score)?.factors ?? [];
  const sum = factors.reduce((total, factor) => (factor.triggered ? total + factor.weight : total), 0);

  return (
    <Panel title={t('card.breakdown.title')} id="breakdown">
      {!score || factors.length === 0 ? (
        <p className="text-text-3">{t('card.breakdown.empty')}</p>
      ) : (
        <>
          <ul>
            {factors.map((factor) => (
              <li
                key={factor.code}
                className={cn(
                  'grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 border-t border-border py-3 first:border-t-0 first:pt-0',
                  factor.triggered && 'pl-3 shadow-[inset_3px_0_0_var(--zone-yellow)]',
                )}
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span
                      className={cn(
                        'inline-flex min-w-7 items-center justify-center rounded-sm px-1.5 text-xs leading-[1.55] font-bold',
                        factor.triggered ? 'bg-primary text-primary-foreground' : 'bg-zone-none-bg text-text-3',
                      )}
                    >
                      {factor.label}
                    </span>
                    <span className={cn(factor.triggered ? 'font-semibold' : 'font-medium text-text-2')}>
                      {e('risk_factor', factor.code)}
                    </span>
                    {factor.triggered ? (
                      <Chip tone="yellow">
                        <IconCheck size={12} stroke={2.4} aria-hidden />
                        {t('card.breakdown.triggered')}
                      </Chip>
                    ) : (
                      <Chip outline>
                        <IconMinus size={12} stroke={2.4} aria-hidden />
                        {t('card.breakdown.notTriggered')}
                      </Chip>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-text-3">{e('risk_factor_desc', factor.code)}</p>
                  <FactorEvidence evidence={factor.evidence} />
                  <details className="group mt-2">
                    <summary className="inline-flex cursor-pointer list-none items-center gap-0.5 text-xs text-text-2 group-open:mb-2 hover:text-text [&::-webkit-details-marker]:hidden">
                      <IconChevronRight
                        className="transition-transform duration-(--dur) group-open:rotate-90"
                        size={14}
                        aria-hidden
                      />
                      {t('card.breakdown.details')}
                    </summary>
                    <FactorDetail detail={factor.detail} />
                  </details>
                </div>
                <div
                  className={cn(
                    'min-w-14 text-right font-heading text-lg tabular-nums',
                    factor.triggered ? 'font-bold' : 'font-normal text-text-3',
                  )}
                >
                  {formatSigned(factor.weight)}
                  {!factor.triggered && (
                    <span className="block font-sans text-2xs font-normal">{t('card.breakdown.notCounted')}</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
          <div className="mt-1 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-t border-border-strong pt-3 text-base">
            <strong className="tabular-nums">{t('card.breakdown.total', { value: score.score })}</strong>
            {sum !== score.score && (
              <span className="text-xs text-text-3">{t('card.breakdown.sumNote', { sum: formatSigned(sum) })}</span>
            )}
          </div>
        </>
      )}
    </Panel>
  );
}
