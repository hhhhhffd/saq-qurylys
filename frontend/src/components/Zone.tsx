import type { Zone } from '@/api/types';
import { Badge } from '@/components/ui/badge';
import { useEnum } from '@/i18n/useEnum';
import { cn } from '@/lib/utils';
import { zoneColor, zoneTone } from './zoneColor';

export function ZoneDot({ zone, size = 10 }: { zone: Zone | null | undefined; size?: number }) {
  return (
    <span
      className="inline-block flex-none rounded-full"
      style={{ background: zoneColor(zone), width: size, height: size }}
      aria-hidden
    />
  );
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
    <Badge variant={tone} className={cn('gap-1.5 tracking-normal normal-case', size === 'md' && 'h-5 px-2 text-2xs')}>
      <ZoneDot zone={zone} size={size === 'md' ? 8 : 7} />
      <span>{e('zone', tone)}</span>
      {score != null && <span className="ml-0.5 border-l border-current pl-1.5 tabular-nums">{score}</span>}
    </Badge>
  );
}
