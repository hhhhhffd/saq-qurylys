import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ScoreHistoryItem } from '@/api/types';
import { zoneColor } from '@/components/zoneColor';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';

const HEIGHT = 220;
const PAD = { left: 30, right: 12, top: 10, bottom: 26 };
const Y_TICKS = [0, 50, 100];
const X_TICKS = 4;
/** Zone score thresholds: below YELLOW_FROM is green, from RED_FROM is red. */
const YELLOW_FROM = 25;
const RED_FROM = 60;
const BANDS = [
  { from: 0, to: YELLOW_FROM, color: 'var(--zone-green-bg)' },
  { from: YELLOW_FROM, to: RED_FROM, color: 'var(--zone-yellow-bg)' },
  { from: RED_FROM, to: 100, color: 'var(--zone-red-bg)' },
];

const round = (value: number) => Math.round(value * 10) / 10;

/**
 * Step chart of the score over time (oldest first) on faint zone bands. Drawn 1:1 in CSS pixels so
 * the labels keep their size; markers only where the zone changes, hover shows the nearest calculation.
 * Nothing is animated, so there is no motion to reduce.
 */
export function ScoreChart({ items }: { items: ScoreHistoryItem[] }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const { date, dateTime } = useFormat();
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const node = wrapRef.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.round(entry.contentRect.width))));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const plotWidth = width - PAD.left - PAD.right;
  const plotHeight = HEIGHT - PAD.top - PAD.bottom;
  const times = items.map((item) => new Date(item.calculated_at).getTime());
  const start = times[0];
  const span = times[times.length - 1] - start;
  const x = (index: number) =>
    round(PAD.left + (span > 0 ? ((times[index] - start) / span) * plotWidth : (index * plotWidth) / (items.length - 1)));
  const y = (score: number) => round(PAD.top + plotHeight * (1 - Math.min(100, Math.max(0, score)) / 100));

  const path = items
    .map((item, index) => (index === 0 ? `M${x(0)},${y(item.score)}` : `H${x(index)}V${y(item.score)}`))
    .join('');
  // Markers only at the ends and where the zone changes.
  const markerIndexes = items.flatMap((item, index) =>
    index === 0 || index === items.length - 1 || item.zone !== items[index - 1].zone ? [index] : [],
  );
  // With no time span there is nothing to spread dates over, so a single tick.
  const xTicks = span > 0 ? Array.from({ length: X_TICKS }, (_, i) => i / (X_TICKS - 1)) : [0];
  const shortDate = (time: number) => date(new Date(time)).slice(0, 5);
  const label = t('card.history.chart', {
    from: dateTime(items[0].calculated_at),
    to: dateTime(items[items.length - 1].calculated_at),
    count: items.length,
  });

  const onPointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const pointer = event.clientX - event.currentTarget.getBoundingClientRect().left;
    let nearest = 0;
    for (let index = 1; index < items.length; index += 1) {
      if (Math.abs(x(index) - pointer) < Math.abs(x(nearest) - pointer)) nearest = index;
    }
    setHover(nearest);
  };

  const hovered = hover === null ? null : items[hover];

  return (
    <div ref={wrapRef} className="relative">
      <svg
        width={width}
        height={HEIGHT}
        className="block touch-pan-y select-none"
        role="img"
        aria-label={label}
        onPointerMove={onPointerMove}
        onPointerLeave={() => setHover(null)}
      >
        {BANDS.map((band) => (
          <rect
            key={band.from}
            x={PAD.left}
            y={y(band.to)}
            width={plotWidth}
            height={y(band.from) - y(band.to)}
            style={{ fill: band.color }}
            opacity={0.45}
          />
        ))}
        {Y_TICKS.map((value) => (
          <g key={value}>
            <line className="stroke-border" strokeWidth={1} opacity={0.7} x1={PAD.left} x2={width - PAD.right} y1={y(value)} y2={y(value)} />
            <text className="fill-text-3" fontSize={11} x={PAD.left - 6} y={y(value)} textAnchor="end" dominantBaseline="middle">
              {value}
            </text>
          </g>
        ))}
        {xTicks.map((fraction) => (
          <text
            key={fraction}
            className="fill-text-3"
            fontSize={11}
            x={round(PAD.left + fraction * plotWidth)}
            y={HEIGHT - 8}
            textAnchor={fraction === 0 ? 'start' : fraction === 1 ? 'end' : 'middle'}
          >
            {shortDate(start + fraction * span)}
          </text>
        ))}
        <path className="fill-none stroke-text-2" strokeWidth={1.25} strokeLinejoin="round" d={path} />
        {markerIndexes.map((index) => (
          <circle
            key={items[index].id}
            className="stroke-surface"
            strokeWidth={1.5}
            cx={x(index)}
            cy={y(items[index].score)}
            r={3.5}
            style={{ fill: zoneColor(items[index].zone) }}
          />
        ))}
        {hover !== null && hovered && (
          <>
            <line className="stroke-text-3" strokeDasharray="3 3" x1={x(hover)} x2={x(hover)} y1={PAD.top} y2={PAD.top + plotHeight} />
            <circle className="stroke-surface" strokeWidth={1.5} cx={x(hover)} cy={y(hovered.score)} r={4.5} style={{ fill: zoneColor(hovered.zone) }} />
          </>
        )}
      </svg>
      {hovered && hover !== null && (
        <div
          className="pointer-events-none absolute top-1 z-10 rounded border border-border bg-surface-raised px-2 py-1 text-xs whitespace-nowrap shadow-window"
          style={x(hover) > width / 2 ? { right: width - x(hover) + 8 } : { left: x(hover) + 8 }}
        >
          {t('card.history.point', { date: dateTime(hovered.calculated_at), score: hovered.score, zone: e('zone', hovered.zone) })}
        </div>
      )}
    </div>
  );
}
