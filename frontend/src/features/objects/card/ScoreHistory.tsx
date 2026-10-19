import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useScoreHistory } from '@/api/hooks/objects';
import { readBreakdown, type ScoreHistoryItem } from '@/api/types';
import { Panel } from '@/components/Panel';
import { EmptyState, QueryBoundary } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { ZoneBadge } from '@/components/Zone';
import { useEnum, useZoneReasonLabel } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { formatSigned } from './formatSigned';
import { ScoreChart } from './ScoreChart';

const CHART_POINTS = 100;
const VISIBLE_ROWS = 10;

const byTime = (a: ScoreHistoryItem, b: ScoreHistoryItem) =>
  new Date(a.calculated_at).getTime() - new Date(b.calculated_at).getTime() || a.id - b.id;

interface HistoryRow {
  latest: ScoreHistoryItem;
  first: ScoreHistoryItem;
  count: number;
}

const rowKey = (item: ScoreHistoryItem) => [item.score, item.zone, ...item.zone_reasons].join('|');

/** Newest first; consecutive calculations with the same score, zone and reasons become one row. */
function collapse(newestFirst: ScoreHistoryItem[]): HistoryRow[] {
  const rows: HistoryRow[] = [];
  for (const item of newestFirst) {
    const last = rows[rows.length - 1];
    if (last && rowKey(last.latest) === rowKey(item)) {
      last.first = item;
      last.count += 1;
    } else {
      rows.push({ latest: item, first: item, count: 1 });
    }
  }
  return rows;
}

function HistoryContent({ items }: { items: ScoreHistoryItem[] }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const reasonLabel = useZoneReasonLabel();
  const { dateTime } = useFormat();
  const [showAll, setShowAll] = useState(false);

  if (items.length === 0) return <EmptyState>{t('card.history.empty')}</EmptyState>;

  const oldestFirst = [...items].sort(byTime);
  const newestFirst = [...oldestFirst].reverse();
  const groups = collapse(newestFirst);
  const rows = showAll ? groups : groups.slice(0, VISIBLE_ROWS);

  return (
    <>
      {oldestFirst.length >= 2 && <ScoreChart items={oldestFirst.slice(-CHART_POINTS)} />}
      <ul className="mt-3 mb-2">
        {rows.map(({ latest: item, first, count }) => {
          const fired = readBreakdown(item)?.factors.filter((factor) => factor.triggered) ?? [];
          return (
            <li key={item.id} className="border-t border-border py-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="tabular-nums">
                  {dateTime(item.calculated_at)}
                  {count > 1 && <span className="ml-2 text-text-3">×{count}</span>}
                </span>
                <ZoneBadge zone={item.zone} score={item.score} />
              </div>
              <p className="mt-1 text-xs text-text-3">
                {[
                  e('score_trigger', item.trigger),
                  item.zone_reasons.length > 0
                    ? item.zone_reasons.map(reasonLabel).join(', ')
                    : t('card.history.noReasons'),
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </p>
              {count > 1 && (
                <p className="mt-1 text-xs text-text-3">{t('card.history.since', { from: dateTime(first.calculated_at) })}</p>
              )}
              {fired.length > 0 && (
                <p className="mt-1 text-xs text-text-3">
                  {t('card.history.fired', {
                    list: fired.map((factor) => `${factor.label} ${formatSigned(factor.weight)}`).join(', '),
                  })}
                </p>
              )}
            </li>
          );
        })}
      </ul>
      {groups.length > VISIBLE_ROWS && (
        <Button variant="ghost" size="sm" onClick={() => setShowAll((value) => !value)}>
          {showAll ? t('card.history.showLess') : t('card.history.showAll', { count: groups.length })}
        </Button>
      )}
    </>
  );
}

export function ScoreHistory({ objectId }: { objectId: number }) {
  const { t } = useTranslation('objects');
  const query = useScoreHistory(objectId);
  return (
    <Panel title={t('card.history.title')} id="history">
      <QueryBoundary query={query}>{(items) => <HistoryContent items={items} />}</QueryBoundary>
    </Panel>
  );
}
