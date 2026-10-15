import { useTranslation } from 'react-i18next';
import type { ScoreHistoryItem } from '@/api/types';
import { zoneColor } from '@/components/zoneColor';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';

const WIDTH = 344;
const HEIGHT = 136;
const PAD = { left: 30, right: 10, top: 10, bottom: 24 };
const GRID_LINES = [0, 50, 100];

const round = (value: number) => Math.round(value * 10) / 10;

/** Step chart of the score per calculation (oldest first, evenly spaced), points colored by zone. */
export function ScoreChart({ items }: { items: ScoreHistoryItem[] }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const { dateTime } = useFormat();

  const plotWidth = WIDTH - PAD.left - PAD.right;
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  const x = (index: number) => round(PAD.left + (index * plotWidth) / (items.length - 1));
  const y = (score: number) => round(PAD.top + plotHeight * (1 - Math.min(100, Math.max(0, score)) / 100));

  const path = items
    .map((item, index) => (index === 0 ? `M${x(0)},${y(item.score)}` : `H${x(index)}V${y(item.score)}`))
    .join('');
  const label = t('card.history.chart', {
    from: dateTime(items[0].calculated_at),
    to: dateTime(items[items.length - 1].calculated_at),
    count: items.length,
  });

  return (
    <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="block h-auto w-full overflow-visible" role="img" aria-label={label}>
      {GRID_LINES.map((value) => (
        <g key={value}>
          <line
            className="stroke-border"
            strokeWidth={1}
            x1={PAD.left}
            x2={WIDTH - PAD.right}
            y1={y(value)}
            y2={y(value)}
          />
          <text className="fill-text-3 text-3xs" x={PAD.left - 6} y={y(value)} textAnchor="end" dominantBaseline="middle">
            {value}
          </text>
        </g>
      ))}
      <path className="fill-none stroke-text-3" strokeWidth={1.5} strokeLinejoin="round" d={path} />
      {items.map((item, index) => (
        <circle
          key={item.id}
          className="stroke-surface"
          strokeWidth={1.5}
          cx={x(index)}
          cy={y(item.score)}
          r={4}
          style={{ fill: zoneColor(item.zone) }}
        >
          <title>
            {t('card.history.point', {
              date: dateTime(item.calculated_at),
              score: item.score,
              zone: e('zone', item.zone),
            })}
          </title>
        </circle>
      ))}
      <text className="fill-text-3 text-3xs" x={PAD.left} y={HEIGHT - 6} textAnchor="start">
        {dateTime(items[0].calculated_at)}
      </text>
      <text className="fill-text-3 text-3xs" x={WIDTH - PAD.right} y={HEIGHT - 6} textAnchor="end">
        {dateTime(items[items.length - 1].calculated_at)}
      </text>
    </svg>
  );
}
