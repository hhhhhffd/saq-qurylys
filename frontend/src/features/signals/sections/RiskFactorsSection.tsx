import { useTranslation } from 'react-i18next';
import type { SignalSections } from '@/api/types';
import { Panel } from '@/components/Panel';
import { useEnum } from '@/i18n/useEnum';
import { DetailList } from './DetailList';
import classes from './Sections.module.css';

function signedWeight(weight: number): string {
  if (weight > 0) return `+${weight}`;
  return weight < 0 ? `−${Math.abs(weight)}` : '0';
}

export function RiskFactorsSection({ items }: { items: SignalSections['risk_factors'] }) {
  const { t } = useTranslation('signals');
  const e = useEnum();
  return (
    <Panel title={t('sections.risk_factors')}>
      {items.length === 0 ? (
        <p className={classes.inlineEmpty}>{t('sections.empty')}</p>
      ) : (
        <ul className={classes.factors}>
          {items.map((item) => (
            <li key={item.code} className={classes.factor}>
              <span className={classes.factorName}>{e('risk_factor', item.code)}</span>
              <span className={classes.weight}>{signedWeight(item.weight)}</span>
              <div className={classes.factorDetail}>
                <DetailList detail={item.detail} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
