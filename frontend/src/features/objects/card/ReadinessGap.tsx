import { useTranslation } from 'react-i18next';
import { Chip } from '@/components/Chip';
import { cn } from '@/lib/utils';
import { formatSigned } from './formatSigned';
import { subTitleClass } from './styles';

interface Props {
  /** readiness from the latest inspection */
  actual: number | null;
  /** readiness from confirmed ads */
  claimed: number | null;
  /** claimed minus actual, percentage points */
  gap: number | null;
  /** the `readiness_overstated` factor fired, i.e. the gap is at or over the threshold */
  overstated: boolean;
}

const clamp = (value: number) => Math.min(100, Math.max(0, value));

/** Actual vs claimed readiness on one bar: the fill is the actual value, the tick is the claim. */
export function ReadinessGap({ actual, claimed, gap, overstated }: Props) {
  const { t } = useTranslation('objects');
  const unknown = t('card.readiness.unknown');
  const pct = (value: number | null) => (value === null ? '—' : `${value}%`);
  const gapText = gap === null ? '—' : `${formatSigned(gap)} ${t('units.pp', { ns: 'common' })}`;
  const summary = t('card.readiness.summary', {
    actual: actual === null ? unknown : pct(actual),
    claimed: claimed === null ? unknown : pct(claimed),
    gap: gap === null ? unknown : gapText,
  });
  const showGap = actual !== null && claimed !== null && claimed > actual;

  return (
    <section className="mt-4 border-t border-border pt-3" aria-labelledby="readiness-gap-title">
      <div className="flex flex-wrap items-center gap-2">
        <h4 id="readiness-gap-title" className={cn(subTitleClass, 'mr-auto')}>
          {t('card.readiness.title')}
        </h4>
        <span
          className={cn(
            'text-base font-bold tabular-nums',
            overstated ? 'text-zone-red-ink' : gap !== null && gap > 0 && 'text-zone-yellow-ink',
          )}
        >
          {gapText}
        </span>
        {overstated && <Chip tone="red">{t('card.readiness.overThreshold')}</Chip>}
      </div>

      <div className="relative mt-3 mb-2.5 h-2.5 rounded-full bg-surface-sunken" role="img" aria-label={summary}>
        {actual !== null && (
          <div className="absolute inset-y-0 left-0 rounded-l-full bg-text-3" style={{ width: `${clamp(actual)}%` }} />
        )}
        {showGap && (
          <div
            className={cn('absolute inset-y-0 opacity-85', overstated ? 'bg-zone-red' : 'bg-zone-yellow')}
            style={{ left: `${clamp(actual)}%`, width: `${clamp(claimed) - clamp(actual)}%` }}
          />
        )}
        {claimed !== null && (
          <div
            className="absolute -inset-y-1 -ml-[1.5px] w-[3px] rounded-[2px] bg-text"
            style={{ left: `${clamp(claimed)}%` }}
          />
        )}
      </div>

      <dl className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <div className="flex items-baseline gap-1.5">
          <dt className="inline-flex items-center gap-1.5 text-text-3">
            <span className="inline-block h-1.5 w-3 flex-none rounded-[3px] bg-text-3" aria-hidden />
            {t('card.readiness.actual')}
          </dt>
          <dd className="font-semibold tabular-nums">{pct(actual)}</dd>
        </div>
        <div className="flex items-baseline gap-1.5">
          <dt className="inline-flex items-center gap-1.5 text-text-3">
            <span className="inline-block h-3 w-[3px] flex-none rounded-[2px] bg-text" aria-hidden />
            {t('card.readiness.claimed')}
          </dt>
          <dd className="font-semibold tabular-nums">{pct(claimed)}</dd>
        </div>
      </dl>
    </section>
  );
}
