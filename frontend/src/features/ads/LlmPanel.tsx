import { Button, Loader } from '@mantine/core';
import { IconAlertTriangle, IconSparkles } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useAcceptLlm } from '@/api/hooks/ads';
import type { AdRow, LlmExtraction } from '@/api/types';
import { Chip } from '@/components/Chip';
import { useEnum } from '@/i18n/useEnum';
import classes from './AdCard.module.css';

interface Props {
  ad: AdRow;
  /** `llm_extraction` of the ad detail; null until it loads */
  extraction: LlmExtraction | null;
  editable: boolean;
}

function StatusLine({ status }: { status: AdRow['llm_status'] }) {
  const e = useEnum();
  return (
    <p className={classes.llmStatus}>
      {status === 'pending' ? (
        <Loader size="xs" />
      ) : status === 'failed' ? (
        <IconAlertTriangle size={14} stroke={1.8} aria-hidden />
      ) : (
        <IconSparkles size={14} stroke={1.8} aria-hidden />
      )}
      {e('llm_status', status)}
    </p>
  );
}

const percent = (value: number) => Math.round(value * 100);

/** Result of the LLM pass: a hypothesis that affects the score only after a human accepts it. */
export function LlmPanel({ ad, extraction, editable }: Props) {
  const { t } = useTranslation('ads');
  const e = useEnum();
  const acceptLlm = useAcceptLlm();

  if (ad.llm_status !== 'done' || !extraction) return <StatusLine status={ad.llm_status} />;

  const schemes = extraction.payment_schemes ?? [];
  const findings = extraction.findings ?? [];
  const readiness = extraction.claimed_readiness_pct;

  return (
    <section className={classes.llm} aria-label={t('llm.badge')}>
      <div className={classes.llmHead}>
        <Chip tone="yellow" outline>
          {t('llm.badge')}
          {extraction.confidence != null && <span className="tnum">{`· ${percent(extraction.confidence)}%`}</span>}
        </Chip>
        {extraction.uncertain && <Chip tone="red">{t('hits.uncertain')}</Chip>}
        <span className="faint">{t('llm.note')}</span>
      </div>
      <dl className={classes.llmList}>
        <div>
          <dt>{t('schemes.label')}</dt>
          <dd>
            {schemes.length > 0 ? (
              <span className={classes.chips}>
                {schemes.map((scheme) => (
                  <Chip key={scheme} outline>
                    {e('payment_scheme', scheme)}
                  </Chip>
                ))}
              </span>
            ) : (
              '—'
            )}
          </dd>
        </div>
        <div>
          <dt>{t('card.readiness')}</dt>
          <dd className="tnum">{readiness != null ? `${readiness}${t('units.pct', { ns: 'common' })}` : '—'}</dd>
        </div>
        <div>
          <dt>{t('card.priceBeforeCompletion')}</dt>
          <dd>{extraction.price_before_completion ? t('yes', { ns: 'common' }) : t('no', { ns: 'common' })}</dd>
        </div>
      </dl>
      {findings.length > 0 && (
        <div>
          <span className={classes.label}>{t('llm.findings')}</span>
          <ul className={classes.quotes}>
            {findings.map((finding, index) => (
              <li key={index}>
                <span>«{finding.quote}»</span>
                <span className={classes.findingMeta}>
                  <span>{e('phrase_category', finding.category)}</span>
                  <span className="tnum">{t('llm.confidence', { value: percent(finding.confidence) })}</span>
                  {finding.uncertain && <Chip tone="red">{t('hits.uncertain')}</Chip>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {editable && (
        <div className={classes.llmActions}>
          <Button size="xs" variant="default" loading={acceptLlm.isPending} onClick={() => acceptLlm.mutate(ad.id)}>
            {t('llm.accept')}
          </Button>
          <span className="faint">{t('llm.acceptHint')}</span>
        </div>
      )}
    </section>
  );
}
