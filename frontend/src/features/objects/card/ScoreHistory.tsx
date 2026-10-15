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

const CHART_POINTS = 30;
const VISIBLE_ROWS = 6;

const byTime = (a: ScoreHistoryItem, b: ScoreHistoryItem) =>
  new Date(a.calculated_at).getTime() - new Date(b.calculated_at).getTime() || a.id - b.id;

function HistoryContent({ items }: { items: ScoreHistoryItem[] }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const reasonLabel = useZoneReasonLabel();
  const { dateTime } = useFormat();
  const [showAll, setShowAll] = useState(false);

  if (items.length === 0) return <EmptyState>{t('card.history.empty')}</EmptyState>;

  const oldestFirst = [...items].sort(byTime);
  const newestFirst = [...oldestFirst].reverse();
  const rows = showAll ? newestFirst : newestFirst.slice(0, VISIBLE_ROWS);

  return (
    <>
      {oldestFirst.length >= 2 && <ScoreChart items={oldestFirst.slice(-CHART_POINTS)} />}
      <ul className="mt-3 mb-2">
        {rows.map((item) => {
          const fired = readBreakdown(item)?.factors.filter((factor) => factor.triggered) ?? [];
          return (
            <li key={item.id} className="border-t border-border py-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="tabular-nums">{dateTime(item.calculated_at)}</span>
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
      {newestFirst.length > VISIBLE_ROWS && (
        <Button variant="ghost" size="sm" onClick={() => setShowAll((value) => !value)}>
          {showAll ? t('card.history.showLess') : t('card.history.showAll', { count: newestFirst.length })}
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
