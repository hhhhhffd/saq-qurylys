import type { Zone } from '@/api/types';
import { useEnum } from '@/i18n/useEnum';
import { zoneColor, zoneTone } from './zoneColor';
import classes from './Zone.module.css';

export function ZoneDot({ zone, size = 10 }: { zone: Zone | null | undefined; size?: number }) {
  return <span className={classes.dot} style={{ background: zoneColor(zone), width: size, height: size }} aria-hidden />;
}

interface BadgeProps {
  zone: Zone | null | undefined;
  /** show the numeric score next to the label */
  score?: number | null;
  size?: 'sm' | 'md';
}

/** Zone label with a dot. The zone is always spelled out, never conveyed by color alone. */
export function ZoneBadge({ zone, score, size = 'sm' }: BadgeProps) {
  const e = useEnum();
  const tone = zoneTone(zone);
  return (
    <span className={`${classes.badge} ${classes[tone]} ${size === 'md' ? classes.md : ''}`}>
      <ZoneDot zone={zone} size={size === 'md' ? 9 : 8} />
      <span>{e('zone', tone)}</span>
      {score != null && <span className={`${classes.score} tnum`}>{score}</span>}
    </span>
  );
}
