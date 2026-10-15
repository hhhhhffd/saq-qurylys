import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { useSettings } from '@/api/hooks/reference';
import { findFactor, readBreakdown, type ObjectDetail, type Zone } from '@/api/types';
import { Chip } from '@/components/Chip';
import { KeyValue } from '@/components/KeyValue';
import { Panel } from '@/components/Panel';
import { LegalBasis } from '@/components/risk/LegalBasis';
import { NeedsCheckList } from '@/components/risk/NeedsCheckList';
import { ZoneBadge, ZoneDot } from '@/components/Zone';
import { zoneColor } from '@/components/zoneColor';
import { useEnum, useZoneReasonLabel } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { ReadinessGap } from './ReadinessGap';
import classes from './RiskPanel.module.css';

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
    <section className={classes.rule} aria-labelledby="zone-rule-title">
      <h4 id="zone-rule-title" className={classes.subTitle}>
        {t('card.risk.rule.title')}
      </h4>
      <ul className={classes.ruleList}>
        {rules.map((rule) => (
          <li key={rule.zone} className={rule.zone === current ? classes.ruleCurrent : undefined}>
            <ZoneDot zone={rule.zone} size={8} />
            <span>{rule.text}</span>
          </li>
        ))}
      </ul>
    </section>
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

  const mismatch = findFactor(breakdown, 'r5_readiness_mismatch');
  const legalChecks =
    findFactor(breakdown, 'r1_no_legal_basis')?.detail.checks ??
    breakdown?.needs_check.find((item) => item.code === 'legal_basis_unknown')?.detail.checks ??
    null;
  // `ads_7d_count` counts the publications of the current analysis window, not of seven days.
  const windowDays = settings?.ad_window_days ?? findFactor(breakdown, 'r3_active_ads')?.detail.window_days;

  return (
    <Panel title={t('card.risk.title')} id="risk">
      {latest ? (
        <>
          <div className={classes.scoreRow}>
            <div className={classes.score}>
              <span className={`${classes.scoreValue} tnum`}>{latest.score}</span>
              <span className={classes.scoreMax}>/ 100</span>
            </div>
            <ZoneBadge zone={latest.zone} size="md" />
          </div>
          <div className={classes.meter} aria-hidden>
            <div
              className={classes.meterFill}
              style={{ width: `${latest.score}%`, background: zoneColor(latest.zone) }}
            />
          </div>

          <section className={classes.reasons} aria-labelledby="risk-reasons-title">
            <h4 id="risk-reasons-title" className={classes.subTitle}>
              {t('card.risk.reasons')}
            </h4>
            {latest.zone_reasons.length > 0 ? (
              <ul className={classes.chips}>
                {latest.zone_reasons.map((code) => (
                  <li key={code}>
                    <Chip tone={latest.zone}>{reasonLabel(code)}</Chip>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={classes.muted}>{t('card.risk.noReasons')}</p>
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
        <p className={classes.muted}>{t('card.risk.notScored')}</p>
      )}

      <ReadinessGap
        actual={object.readiness_actual_pct}
        claimed={object.readiness_claimed_pct}
        gap={object.readiness_gap_pp}
        overstated={mismatch?.triggered ?? false}
      />

      <div className={classes.facts}>
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
                <span className="tnum">
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
}
