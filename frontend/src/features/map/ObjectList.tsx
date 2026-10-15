import { useState } from 'react';
import { Button } from '@mantine/core';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import type { ObjectRow } from '@/api/types';
import { EmptyState } from '@/components/QueryState';
import { ZoneBadge } from '@/components/Zone';
import { useKeyStatusLabel } from '@/i18n/useEnum';
import classes from './ObjectList.module.css';

/** Thousands of rows would make the page sluggish, so the list grows in steps. */
const STEP = 100;

interface Props {
  rows: ObjectRow[];
  /** row under the pointer or focus; its marker is highlighted on the map */
  highlightedId: number | null;
  onHighlight: (id: number | null) => void;
}

export function ObjectList({ rows, highlightedId, onHighlight }: Props) {
  const { t } = useTranslation('map');
  const keyStatus = useKeyStatusLabel();
  const [shown, setShown] = useState(STEP);

  if (rows.length === 0) {
    return (
      <EmptyState>
        {t('list.empty')}
        <br />
        <span className="faint">{t('list.emptyHint')}</span>
      </EmptyState>
    );
  }

  return (
    <>
      <ul className={classes.list}>
        {rows.slice(0, shown).map((row) => (
          <li key={row.id} onMouseEnter={() => onHighlight(row.id)} onMouseLeave={() => onHighlight(null)}>
            <Link
              to={`/objects/${row.id}`}
              className={classes.row}
              data-active={highlightedId === row.id || undefined}
              onFocus={() => onHighlight(row.id)}
              onBlur={() => onHighlight(null)}
            >
              <span className={classes.head}>
                <span className={classes.name}>{row.name}</span>
                <ZoneBadge zone={row.zone} score={row.score} />
              </span>
              <span className={classes.meta}>
                <span className="tnum">{row.code}</span>
                {row.developer_name && <span>{row.developer_name}</span>}
              </span>
              <span className={classes.foot}>
                <span>{keyStatus(row.key_status, row.key_status_detail)}</span>
                {row.district_name && <span className="faint">{row.district_name}</span>}
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {rows.length > shown && (
        <div className={classes.more}>
          <Button variant="subtle" size="xs" onClick={() => setShown((count) => count + STEP)}>
            {t('list.showMore', { count: rows.length - shown })}
          </Button>
        </div>
      )}
    </>
  );
}
