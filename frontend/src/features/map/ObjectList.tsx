import { useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import type { ObjectRow } from '@/api/types';
import { Button } from '@/components/ui/button';
import BorderGlow from '@/components/fx/BorderGlow';
import { EmptyState } from '@/components/QueryState';
import { ZoneBadge } from '@/components/Zone';
import { useKeyStatusLabel } from '@/i18n/useEnum';

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
        <span className="text-text-3">{t('list.emptyHint')}</span>
      </EmptyState>
    );
  }

  return (
    <>
      <ul className="m-0 list-none p-0">
        {rows.slice(0, shown).map((row) => {
          const link = (
            <Link
              to={`/objects/${row.id}`}
              className="flex flex-col gap-0.5 px-3 py-1.5 text-text no-underline outline-none transition-colors duration-(--dur) hover:bg-hover focus-visible:bg-hover focus-visible:ring-1 focus-visible:ring-focus focus-visible:ring-inset active:bg-pressed data-active:bg-hover"
              data-active={highlightedId === row.id || undefined}
              onFocus={() => onHighlight(row.id)}
              onBlur={() => onHighlight(null)}
            >
              <span className="flex items-start justify-between gap-2.5">
                <span className="min-w-0 text-sm font-semibold wrap-anywhere">{row.name}</span>
                <ZoneBadge zone={row.zone} score={row.score} />
              </span>
              <span className="flex flex-wrap gap-x-2.5 gap-y-0.5 text-xs text-text-2">
                <span className="tabular-nums">{row.code}</span>
                {row.developer_name && <span>{row.developer_name}</span>}
              </span>
              <span className="flex flex-wrap justify-between gap-x-2.5 gap-y-0.5 text-xs text-text-2">
                <span>{keyStatus(row.key_status, row.key_status_detail)}</span>
                {row.district_name && <span className="text-text-3">{row.district_name}</span>}
              </span>
            </Link>
          );
          return (
            <li
              key={row.id}
              className="border-t border-border first:border-t-0"
              onMouseEnter={() => onHighlight(row.id)}
              onMouseLeave={() => onHighlight(null)}
            >
              {row.zone === 'red' ? (
                // Red-zone rows glow along the border near the pointer; at rest the border is calm.
                <BorderGlow className="mx-1 my-0.5" borderRadius={4} glowColor="5 100 62" glowIntensity={0.7}>
                  {link}
                </BorderGlow>
              ) : (
                link
              )}
            </li>
          );
        })}
      </ul>
      {rows.length > shown && (
        <div className="flex justify-center border-t border-border p-2">
          <Button variant="ghost" size="xs" onClick={() => setShown((count) => count + STEP)}>
            {t('list.showMore', { count: rows.length - shown })}
          </Button>
        </div>
      )}
    </>
  );
}
