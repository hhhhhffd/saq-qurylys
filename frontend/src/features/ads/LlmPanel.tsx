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

/** Result of the LLM pass: an assumption that affects the score only after a human accepts it. */
export function LlmPanel({ ad, extraction, editable }: Props) {
  const { t } = useTranslation('ads');
  const e = useEnum();
  const acceptLlm = useAcceptLlm();

  if (ad.llm_status !== 'done' || !extraction) return <StatusLine status={ad.llm_status} />;

  const schemes = extraction.payment_schemes ?? [];
  const quotes = extraction.quotes ?? [];
  const readiness = extraction.claimed_readiness_pct;

  return (
    <section className={classes.llm} aria-label={t('llm.badge')}>
      <div className={classes.llmHead}>
        <Chip outline>{t('llm.badge')}</Chip>
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
      {quotes.length > 0 && (
        <div>
          <span className={classes.label}>{t('llm.quotes')}</span>
          <ul className={classes.quotes}>
            {quotes.map((quote, index) => (
              <li key={index}>«{quote}»</li>
            ))}
          </ul>
        </div>
      )}
      {editable && (
        <div>
          <Button size="xs" variant="default" loading={acceptLlm.isPending} onClick={() => acceptLlm.mutate(ad.id)}>
            {t('llm.accept')}
          </Button>
        </div>
      )}
    </section>
  );
}
