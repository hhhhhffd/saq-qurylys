import { useTranslation } from 'react-i18next';
import type { DashboardCounts, Zone } from '@/api/types';
import CountUp from '@/components/fx/CountUp';
import { useEnum } from '@/i18n/useEnum';
import { ZONES } from '@/features/objects/list/filters';
import { cn } from '@/lib/utils';

interface Props {
  counts: DashboardCounts;
  /** zone the list and the map are narrowed to */
  active: Zone | null;
  onToggle: (zone: Zone) => void;
  /** count up on load; off while the time machine rewrites the numbers every frame */
  animated?: boolean;
}

const ZONE_TONE: Record<Zone, string> = {
  green: 'border-zone-green/30 bg-zone-green-bg text-zone-green-ink',
  yellow: 'border-zone-yellow/30 bg-zone-yellow-bg text-zone-yellow-ink',
  red: 'border-zone-red/30 bg-zone-red-bg text-zone-red-ink',
};

const CARD = 'flex flex-col gap-0.5 rounded border px-3 py-2 text-left';
const VALUE = 'font-heading text-2xl leading-tight font-bold tabular-nums';
// Not uppercase: e2e reads the counters through innerText, which applies text-transform.
const LABEL = 'text-xs font-semibold tracking-wide';

/** Zone counters double as toggle buttons that narrow the list and the map. */
export function ZoneCounters({ counts, active, onToggle, animated = true }: Props) {
  const { t } = useTranslation('map');
  const { t: common } = useTranslation();
  const e = useEnum();

  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4 md:gap-3" role="group" aria-label={t('counters.label')}>
      {ZONES.map((zone) => (
        <button
          key={zone}
          type="button"
          className={cn(
            CARD,
            ZONE_TONE[zone],
            'cursor-pointer outline-none transition-[box-shadow,filter,border-color] duration-(--dur) hover:brightness-125 focus-visible:ring-1 focus-visible:ring-focus',
            'aria-pressed:border-primary aria-pressed:shadow-glow',
          )}
          aria-pressed={active === zone}
          onClick={() => onToggle(zone)}
        >
          <span className={VALUE}>{animated ? <CountUp to={counts[zone]} duration={1.2} /> : counts[zone]}</span>
          <span className={LABEL}>{e('zone', zone)}</span>
        </button>
      ))}
      <div className={cn(CARD, 'border-border bg-surface text-text')}>
        <span className={VALUE}>{animated ? <CountUp to={counts.total} duration={1.2} /> : counts.total}</span>
        <span className={LABEL}>{common('total')}</span>
        {counts.unscored > 0 && <span className="text-xs text-text-2">{t('counters.unscored', { count: counts.unscored })}</span>}
      </div>
    </div>
  );
}
