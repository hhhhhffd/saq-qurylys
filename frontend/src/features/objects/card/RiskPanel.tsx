import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { useSettings } from '@/api/hooks/reference';
import { findFactor, readBreakdown, type ObjectDetail, type RiskBreakdown, type Zone } from '@/api/types';
import { Chip } from '@/components/Chip';
import { KeyValue } from '@/components/KeyValue';
import { Panel } from '@/components/Panel';
import BorderGlow from '@/components/fx/BorderGlow';
import CountUp from '@/components/fx/CountUp';
import { LegalBasis } from '@/components/risk/LegalBasis';
import { NeedsCheckList } from '@/components/risk/NeedsCheckList';
import { ZoneBadge, ZoneDot } from '@/components/Zone';
import { zoneColor } from '@/components/zoneColor';
import { useEnum, useZoneReasonLabel } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { cn } from '@/lib/utils';
import { ReadinessGap } from './ReadinessGap';
import { anchorTargetClass, subTitleClass } from './styles';

// Defaults of `zone_yellow_min` / `zone_red_min` (SPEC 6.2) while the settings are not loaded.
const DEFAULT_YELLOW_MIN = 25;
const DEFAULT_RED_MIN = 60;

function ZoneRule({ yellowMin, redMin, current }: { yellowMin: number; redMin: number; current: Zone }) {
  const { t } = useTranslation('objects');
  const rules: { zone: Zone; text: string }[] = [
    { zone: 'green', text: t('card.risk.rule.green', { to: yellowMin - 1 }) },
    { zone: 'yellow', text: t('card.risk.rule.yellow', { from: yellowMin, to: redMin - 1, red: redMin }) },
    { zone: 'red', text: t('card.risk.rule.red', { red: redMin }) },
  ];
  return (
    <section className="mt-4" aria-labelledby="zone-rule-title">
      <h4 id="zone-rule-title" className={cn(subTitleClass, 'mb-2')}>
        {t('card.risk.rule.title')}
      </h4>
      <ul className="flex flex-col gap-1 text-xs text-text-3">
        {rules.map((rule) => (
          <li key={rule.zone} className={cn('flex items-center gap-2', rule.zone === current && 'font-semibold text-text')}>
            <ZoneDot zone={rule.zone} size={8} />
            <span>{rule.text}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

const SUMMARY_FACTORS_MAX = 3;
const SUMMARY_CHECKS_MAX = 2;

/** Two plain sentences: why the zone is what it is, and what the employee should check first. */
function RiskSummary({ zone, breakdown }: { zone: Zone; breakdown: RiskBreakdown | null }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const lower = (text: string) => text.toLocaleLowerCase();

  const factors = (breakdown?.factors ?? [])
    .filter((factor) => factor.triggered)
    .sort((a, b) => b.weight - a.weight)
    .slice(0, SUMMARY_FACTORS_MAX)
    .map((factor) => lower(e('risk_factor', factor.code)));
  const reason = factors.length > 0 ? factors.join('; ') : t(`card.risk.summary.noFactors.${zone}`);

  const checks = (breakdown?.needs_check ?? [])
    .slice(0, SUMMARY_CHECKS_MAX)
    .map((item) => lower(e('needs_check', item.code)));
  const todo =
    zone === 'green'
      ? t('card.risk.summary.noChecks')
      : checks.length > 0
        ? t('card.risk.summary.check', { items: checks.join('; ') })
        : t('card.risk.summary.checkGeneric');

  return (
    <div
      className="mt-4 rounded-md border border-border bg-surface-sunken p-3 text-base leading-snug"
      data-testid="risk-plain-summary"
    >
      <p className="m-0 font-semibold">
        {t('card.risk.summary.why', { zone: t(`card.risk.summary.zone.${zone}`), reason })}
      </p>
      <p className="m-0 mt-1.5 text-text-2">{todo}</p>
    </div>
  );
}

export function RiskPanel({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const reasonLabel = useZoneReasonLabel();
  const { dateTime } = useFormat();
  const settings = useSettings().data;
  const latest = object.latest_score;
  const breakdown = readBreakdown(latest);
  const red = latest?.zone === 'red';

  const mismatch = findFactor(breakdown, 'r5_readiness_mismatch');
  const legalChecks =
    findFactor(breakdown, 'r1_no_legal_basis')?.detail.checks ??
    breakdown?.needs_check.find((item) => item.code === 'legal_basis_unknown')?.detail.checks ??
    null;
  // `ads_7d_count` counts the publications of the current analysis window, not of seven days.
  const windowDays = settings?.ad_window_days ?? findFactor(breakdown, 'r3_active_ads')?.detail.window_days;

  const panel = (
    // In the red zone the glow draws the frame, so the panel gives up its own.
    <Panel
      title={t('card.risk.title')}
      id="risk"
      className={cn(anchorTargetClass, red && 'border-0! bg-transparent! shadow-none!')}
    >
      {latest ? (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3" data-testid="risk-summary">
            <div className="flex items-baseline gap-1.5">
              <span className="font-heading text-5xl leading-none font-bold tracking-tight tabular-nums">
                <CountUp key={latest.calculated_at}to={latest.score} duration={1.2} />
              </span>
              <span className="text-sm text-text-3">/ 100</span>
            </div>
            <ZoneBadge zone={latest.zone} size="md" />
          </div>
          <div className="mt-3 h-1 overflow-hidden rounded-full bg-surface-sunken" aria-hidden>
            <div
              className="h-full rounded-full"
              style={{ width: `${latest.score}%`, background: zoneColor(latest.zone) }}
            />
          </div>

          <RiskSummary zone={latest.zone} breakdown={breakdown} />

          <section className="mt-4" aria-labelledby="risk-reasons-title">
            <h4 id="risk-reasons-title" className={cn(subTitleClass, 'mb-2')}>
              {t('card.risk.reasons')}
            </h4>
            {latest.zone_reasons.length > 0 ? (
              <ul className="flex flex-wrap gap-1.5">
                {latest.zone_reasons.map((code) => (
                  <li key={code}>
                    <Chip tone={latest.zone}>{reasonLabel(code)}</Chip>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-text-3">{t('card.risk.noReasons')}</p>
            )}
          </section>

          <ZoneRule
            yellowMin={settings?.zone_yellow_min ?? DEFAULT_YELLOW_MIN}
            redMin={settings?.zone_red_min ?? DEFAULT_RED_MIN}
            current={latest.zone}
          />

          {breakdown && <LegalBasis status={breakdown.legal_basis_status} checks={legalChecks} />}
          {breakdown && <NeedsCheckList items={breakdown.needs_check} />}
        </>
      ) : (
        <p className="text-text-3">{t('card.risk.notScored')}</p>
      )}

      <ReadinessGap
        actual={object.readiness_actual_pct}
        claimed={object.readiness_claimed_pct}
        gap={object.readiness_gap_pp}
        overstated={mismatch?.triggered ?? false}
      />

      <div className="mt-4 border-t border-border pt-3">
        <KeyValue
          columns={1}
          items={[
            {
              label: windowDays === undefined ? t('card.risk.adsPeriod') : t('card.risk.ads', { count: windowDays }),
              value:
                object.ads_7d_count > 0 ? (
                  <Link to={`/ads?object_id=${object.id}`}>
                    {t('card.risk.publications', { count: object.ads_7d_count })}
                  </Link>
                ) : (
                  t('card.risk.publications', { count: 0 })
                ),
            },
            {
              label: t('card.risk.calculatedAt'),
              value: latest && (
                <span className="tabular-nums">
                  {dateTime(latest.calculated_at)}
                  {latest.trigger && ` · ${e('score_trigger', latest.trigger)}`}
                </span>
              ),
            },
          ]}
        />
      </div>
    </Panel>
  );

  return red ? (
    <BorderGlow glowColor="5 100 62" colors={['var(--zone-red-ink)', 'var(--accent-text)', 'var(--zone-red)']}>
      {panel}
    </BorderGlow>
  ) : (
    panel
  );
}
