import { IconCheck, IconChevronRight, IconMinus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { readBreakdown, type RiskScore } from '@/api/types';
import { Chip } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { FactorDetail } from '@/components/risk/FactorDetail';
import { FactorEvidence } from '@/components/risk/FactorEvidence';
import { useEnum } from '@/i18n/useEnum';
import { formatSigned } from './formatSigned';
import classes from './BreakdownList.module.css';

export function BreakdownList({ score }: { score: RiskScore | null }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const factors = readBreakdown(score)?.factors ?? [];
  const sum = factors.reduce((total, factor) => (factor.triggered ? total + factor.weight : total), 0);

  return (
    <Panel title={t('card.breakdown.title')} id="breakdown">
      {!score || factors.length === 0 ? (
        <p className={classes.muted}>{t('card.breakdown.empty')}</p>
      ) : (
        <>
          <ul className={classes.list}>
            {factors.map((factor) => (
              <li key={factor.code} className={`${classes.factor} ${factor.triggered ? classes.on : classes.off}`}>
                <div className={classes.main}>
                  <div className={classes.head}>
                    <span className={classes.label}>{factor.label}</span>
                    <span className={classes.name}>{e('risk_factor', factor.code)}</span>
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
                  <p className={classes.desc}>{e('risk_factor_desc', factor.code)}</p>
                  <FactorEvidence evidence={factor.evidence} />
                  <details className={classes.details}>
                    <summary>
                      <IconChevronRight className={classes.chevron} size={14} aria-hidden />
                      {t('card.breakdown.details')}
                    </summary>
                    <FactorDetail detail={factor.detail} />
                  </details>
                </div>
                <div className={`${classes.weight} tnum`}>
                  {formatSigned(factor.weight)}
                  {!factor.triggered && <span className={classes.notCounted}>{t('card.breakdown.notCounted')}</span>}
                </div>
              </li>
            ))}
          </ul>
          <div className={classes.total}>
            <strong className="tnum">{t('card.breakdown.total', { value: score.score })}</strong>
            {sum !== score.score && (
              <span className={classes.totalNote}>{t('card.breakdown.sumNote', { sum: formatSigned(sum) })}</span>
            )}
          </div>
        </>
      )}
    </Panel>
  );
}
