import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import type { ObjectDetail } from '@/api/types';
import { Chip } from '@/components/Chip';
import { KeyValue } from '@/components/KeyValue';
import { Panel } from '@/components/Panel';
import { ZoneBadge } from '@/components/Zone';
import { zoneColor } from '@/components/zoneColor';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { ReadinessGap } from './ReadinessGap';
import classes from './RiskPanel.module.css';

export function RiskPanel({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const { dateTime } = useFormat();
  const latest = object.latest_score;
  const overstated = latest?.breakdown.some((factor) => factor.code === 'readiness_overstated' && factor.triggered);

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
            <div className={classes.meterFill} style={{ width: `${latest.score}%`, background: zoneColor(latest.zone) }} />
          </div>

          <section className={classes.reasons} aria-labelledby="risk-reasons-title">
            <h4 id="risk-reasons-title" className={classes.subTitle}>
              {t('card.risk.reasons')}
            </h4>
            {latest.zone_reasons.length > 0 ? (
              <ul className={classes.chips}>
                {latest.zone_reasons.map((code) => (
                  <li key={code}>
                    <Chip tone={latest.zone}>{e('zone_reason', code)}</Chip>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={classes.muted}>{t('card.risk.noReasons')}</p>
            )}
          </section>
        </>
      ) : (
        <p className={classes.muted}>{t('card.risk.notScored')}</p>
      )}

      <ReadinessGap
        actual={object.readiness_actual_pct}
        claimed={object.readiness_claimed_pct}
        gap={object.readiness_gap_pp}
        overstated={Boolean(overstated)}
      />

      <div className={classes.facts}>
        <KeyValue
          columns={1}
          items={[
            {
              label: t('card.risk.ads'),
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
