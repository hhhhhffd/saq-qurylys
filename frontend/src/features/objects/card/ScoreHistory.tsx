import { useState } from 'react';
import { Button } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { useScoreHistory } from '@/api/hooks/objects';
import type { ScoreHistoryItem } from '@/api/types';
import { Panel } from '@/components/Panel';
import { EmptyState, QueryBoundary } from '@/components/QueryState';
import { ZoneBadge } from '@/components/Zone';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { ScoreChart } from './ScoreChart';
import classes from './ScoreHistory.module.css';

const CHART_POINTS = 30;
const VISIBLE_ROWS = 6;

const byTime = (a: ScoreHistoryItem, b: ScoreHistoryItem) =>
  new Date(a.calculated_at).getTime() - new Date(b.calculated_at).getTime() || a.id - b.id;

function HistoryContent({ items }: { items: ScoreHistoryItem[] }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const { dateTime } = useFormat();
  const [showAll, setShowAll] = useState(false);

  if (items.length === 0) return <EmptyState>{t('card.history.empty')}</EmptyState>;

  const oldestFirst = [...items].sort(byTime);
  const newestFirst = [...oldestFirst].reverse();
  const rows = showAll ? newestFirst : newestFirst.slice(0, VISIBLE_ROWS);

  return (
    <>
      {oldestFirst.length >= 2 && <ScoreChart items={oldestFirst.slice(-CHART_POINTS)} />}
      <ul className={classes.list}>
        {rows.map((item) => (
          <li key={item.id} className={classes.row}>
            <div className={classes.rowHead}>
              <span className="tnum">{dateTime(item.calculated_at)}</span>
              <ZoneBadge zone={item.zone} score={item.score} />
            </div>
            <p className={classes.rowMeta}>
              {[
                e('score_trigger', item.trigger),
                item.zone_reasons.length > 0
                  ? item.zone_reasons.map((code) => e('zone_reason', code)).join(', ')
                  : t('card.history.noReasons'),
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
          </li>
        ))}
      </ul>
      {newestFirst.length > VISIBLE_ROWS && (
        <Button variant="subtle" size="compact-sm" onClick={() => setShowAll((value) => !value)}>
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
