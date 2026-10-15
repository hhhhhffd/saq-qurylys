import { IconAlertTriangle, IconSparkles } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useAcceptLlm } from '@/api/hooks/ads';
import type { AdRow, LlmExtraction } from '@/api/types';
import { Chip } from '@/components/Chip';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { useEnum } from '@/i18n/useEnum';

interface Props {
  ad: AdRow;
  /** `llm_extraction` of the ad detail; null until it loads */
  extraction: LlmExtraction | null;
  editable: boolean;
}

function StatusLine({ status }: { status: AdRow['llm_status'] }) {
  const e = useEnum();
  return (
    <p className="m-0 flex items-center gap-1.5 text-sm text-text-3 [&>svg]:size-3.5">
      {status === 'pending' ? (
        <Spinner className="size-3.5" />
      ) : status === 'failed' ? (
        <IconAlertTriangle aria-hidden />
      ) : (
        <IconSparkles aria-hidden />
      )}
      {e('llm_status', status)}
    </p>
  );
}

const percent = (value: number) => Math.round(value * 100);

const termClass = 'text-xs font-medium text-text-3';

/**
 * Result of the LLM pass: a hypothesis that affects the score only after a human accepts it. The violet border sets
 * it apart from the confirmed facts around it.
 */
export function LlmPanel({ ad, extraction, editable }: Props) {
  const { t } = useTranslation('ads');
  const e = useEnum();
  const acceptLlm = useAcceptLlm();

  if (ad.llm_status !== 'done' || !extraction) return <StatusLine status={ad.llm_status} />;

  const schemes = extraction.payment_schemes ?? [];
  const findings = extraction.findings ?? [];
  const readiness = extraction.claimed_readiness_pct;

  return (
    <section
      className="flex flex-col gap-2.5 rounded border border-graph-developer/50 bg-graph-developer/6 px-3.5 py-3 text-sm"
      aria-label={t('llm.badge')}
    >
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <Chip tone="yellow" outline>
          {t('llm.badge')}
          {extraction.confidence != null && <span className="tabular-nums">{`· ${percent(extraction.confidence)}%`}</span>}
        </Chip>
        {extraction.uncertain && <Chip tone="red">{t('hits.uncertain')}</Chip>}
        <span className="text-text-3">{t('llm.note')}</span>
      </div>
      <dl className="m-0 grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-x-4 gap-y-2">
        <div>
          <dt className={termClass}>{t('schemes.label')}</dt>
          <dd className="m-0 mt-0.5">
            {schemes.length > 0 ? (
              <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1.5">
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
          <dt className={termClass}>{t('card.readiness')}</dt>
          <dd className="m-0 mt-0.5 tabular-nums">
            {readiness != null ? `${readiness}${t('units.pct', { ns: 'common' })}` : '—'}
          </dd>
        </div>
        <div>
          <dt className={termClass}>{t('card.priceBeforeCompletion')}</dt>
          <dd className="m-0 mt-0.5">
            {extraction.price_before_completion ? t('yes', { ns: 'common' }) : t('no', { ns: 'common' })}
          </dd>
        </div>
      </dl>
      {findings.length > 0 && (
        <div>
          <span className={termClass}>{t('llm.findings')}</span>
          <ul className="m-0 mt-1 flex list-none flex-col gap-1.5 border-l-2 border-graph-developer/50 py-0 pr-0 pl-3.5 [overflow-wrap:anywhere]">
            {findings.map((finding, index) => (
              <li key={index}>
                <span>«{finding.quote}»</span>
                <span className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-xs text-text-2">
                  <span>{e('phrase_category', finding.category)}</span>
                  <span className="tabular-nums">{t('llm.confidence', { value: percent(finding.confidence) })}</span>
                  {finding.uncertain && <Chip tone="red">{t('hits.uncertain')}</Chip>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {editable && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <Button size="sm" variant="secondary" loading={acceptLlm.isPending} onClick={() => acceptLlm.mutate(ad.id)}>
            {t('llm.accept')}
          </Button>
          <span className="text-text-3">{t('llm.acceptHint')}</span>
        </div>
      )}
    </section>
  );
}
