import { useTranslation } from 'react-i18next';
import { Chip } from '@/components/Chip';
import { formatSigned } from './formatSigned';
import classes from './ReadinessGap.module.css';

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
    <section className={classes.root} aria-labelledby="readiness-gap-title">
      <div className={classes.head}>
        <h4 id="readiness-gap-title" className={classes.title}>
          {t('card.readiness.title')}
        </h4>
        <span
          className={`${classes.gap} tnum ${overstated ? classes.danger : gap !== null && gap > 0 ? classes.warn : ''}`}
        >
          {gapText}
        </span>
        {overstated && <Chip tone="red">{t('card.readiness.overThreshold')}</Chip>}
      </div>

      <div className={classes.bar} role="img" aria-label={summary}>
        {actual !== null && <div className={classes.actual} style={{ width: `${clamp(actual)}%` }} />}
        {showGap && (
          <div
            className={`${classes.gapSegment} ${overstated ? classes.gapDanger : classes.gapWarn}`}
            style={{ left: `${clamp(actual)}%`, width: `${clamp(claimed) - clamp(actual)}%` }}
          />
        )}
        {claimed !== null && <div className={classes.claimed} style={{ left: `${clamp(claimed)}%` }} />}
      </div>

      <dl className={classes.legend}>
        <div>
          <dt>
            <span className={classes.swatchActual} aria-hidden />
            {t('card.readiness.actual')}
          </dt>
          <dd className="tnum">{pct(actual)}</dd>
        </div>
        <div>
          <dt>
            <span className={classes.swatchClaimed} aria-hidden />
            {t('card.readiness.claimed')}
          </dt>
          <dd className="tnum">{pct(claimed)}</dd>
        </div>
      </dl>
    </section>
  );
}
