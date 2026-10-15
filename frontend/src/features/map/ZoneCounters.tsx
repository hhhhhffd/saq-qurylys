import { useTranslation } from 'react-i18next';
import type { DashboardCounts, Zone } from '@/api/types';
import { useEnum } from '@/i18n/useEnum';
import { ZONES } from '@/features/objects/list/filters';
import classes from './ZoneCounters.module.css';

interface Props {
  counts: DashboardCounts;
  /** zone the list and the map are narrowed to */
  active: Zone | null;
  onToggle: (zone: Zone) => void;
}

/** Zone counters double as toggle buttons that narrow the list and the map. */
export function ZoneCounters({ counts, active, onToggle }: Props) {
  const { t } = useTranslation('map');
  const { t: common } = useTranslation();
  const e = useEnum();

  return (
    <div className={classes.root} role="group" aria-label={t('counters.label')}>
      {ZONES.map((zone) => (
        <button
          key={zone}
          type="button"
          className={`${classes.card} ${classes.toggle} ${classes[zone]}`}
          aria-pressed={active === zone}
          onClick={() => onToggle(zone)}
        >
          <span className={`${classes.value} tnum`}>{counts[zone]}</span>
          <span className={classes.label}>{e('zone', zone)}</span>
        </button>
      ))}
      <div className={`${classes.card} ${classes.total}`}>
        <span className={`${classes.value} tnum`}>{counts.total}</span>
        <span className={classes.label}>{common('total')}</span>
        {counts.unscored > 0 && <span className={classes.note}>{t('counters.unscored', { count: counts.unscored })}</span>}
      </div>
    </div>
  );
}
