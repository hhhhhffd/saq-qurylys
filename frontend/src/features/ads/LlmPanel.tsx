import { IconAlertTriangle, IconSparkles } from '@tabler/icons-react';
import { useState } from 'react';
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
  const { t } = useTranslation('ads');
  const message = status === 'pending' ? t('llm.statusPending') : status === 'failed' ? t('llm.statusFailed') : t('llm.statusUnavailable');
  return (
    <p className="m-0 flex items-start gap-1.5 text-sm text-text-2 [&>svg]:mt-0.5 [&>svg]:size-3.5" role={status === 'failed' ? 'alert' : 'status'}>
      {status === 'pending' ? (
        <Spinner className="size-3.5" />
      ) : status === 'failed' ? (
        <IconAlertTriangle aria-hidden />
      ) : (
        <IconSparkles aria-hidden />
      )}
      <span>{message}</span>
    </p>
  );
}

const percent = (value: number) => Math.round(value * 100);

const termClass = 'text-xs font-medium text-text-3';

/**
 * Result of the LLM pass: a hypothesis that affects the score only after a human accepts it. The amber treatment
 * keeps suggestions distinct from confirmed facts.
 */
export function LlmPanel({ ad, extraction, editable }: Props) {
  const { t } = useTranslation('ads');
  const e = useEnum();
  const acceptLlm = useAcceptLlm();
  const [accepted, setAccepted] = useState(false);

  if (ad.llm_status !== 'done') return <StatusLine status={ad.llm_status} />;
  if (!extraction) return null;

  const schemes = extraction.payment_schemes;
  const findings = extraction.findings ?? [];
  const readiness = extraction.claimed_readiness_pct;

  return (
    <section
      className="flex flex-col gap-2.5 rounded border border-zone-yellow/50 bg-zone-yellow-bg px-3.5 py-3 text-sm"
      aria-label={t('llm.badge')}
    >
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <Chip tone="yellow" outline>
          {t('llm.badge')}
        </Chip>
        {extraction.uncertain && <Chip tone="red">{t('hits.uncertain')}</Chip>}
        <span className="text-text-2">{t('llm.note')}</span>
      </div>
      {findings.length > 0 && (
        <div>
          <span className={termClass}>{t('llm.findings')}</span>
          <ul className="m-0 mt-1 flex list-none flex-col gap-1.5 border-l-2 border-zone-yellow/50 py-0 pr-0 pl-3.5 [overflow-wrap:anywhere]">
            {findings.map((finding, index) => (
              <li key={index}>
                <span>«{finding.quote}»</span>
                <span className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-xs text-text-2">
                  <span>{e('phrase_category', finding.category)}</span>
                  {finding.uncertain && <Chip tone="red">{t('hits.uncertain')}</Chip>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <span className={termClass}>{t('llm.fieldsTitle')}</span>
        <dl className="m-0 mt-1 grid grid-cols-[repeat(auto-fit,minmax(min(100%,180px),1fr))] gap-x-4 gap-y-2">
          <div>
            <dt className={termClass}>{t('schemes.label')}</dt>
            <dd className="m-0 mt-0.5">
              {schemes === undefined ? (
                t('llm.valueUnknown')
              ) : schemes.length > 0 ? (
                <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1.5">
                  {schemes.map((scheme) => (
                    <Chip key={scheme} outline>{e('payment_scheme', scheme)}</Chip>
                  ))}
                </span>
              ) : t('llm.noSchemes')}
            </dd>
          </div>
          <div>
            <dt className={termClass}>{t('card.readiness')}</dt>
            <dd className="m-0 mt-0.5 tabular-nums">
              {readiness === null || readiness === undefined
                ? t('llm.readinessMissing')
                : `${readiness}${t('units.pct', { ns: 'common' })}`}
            </dd>
          </div>
          <div>
            <dt className={termClass}>{t('card.priceBeforeCompletion')}</dt>
            <dd className="m-0 mt-0.5">
              {typeof extraction.price_before_completion !== 'boolean'
                ? t('llm.valueUnknown')
                : t(extraction.price_before_completion ? 'llm.priceClaimFound' : 'llm.priceClaimNotFound')}
            </dd>
          </div>
        </dl>
      </div>
      {extraction.confidence != null && (
        <details className="text-sm">
          <summary className="inline-flex cursor-pointer items-center text-text-2 hover:text-text max-sm:min-h-11">
            {t('llm.details')}
          </summary>
          <p className="m-0 mt-1 text-xs text-text-3 tabular-nums">
            {t('llm.confidenceLabel')}: {percent(extraction.confidence)}%
          </p>
        </details>
      )}
      {editable && (
        <div className="flex flex-col items-start gap-2">
          {accepted ? (
            <p className="m-0 text-sm text-zone-green-ink" role="status">{t('llm.acceptedFeedback')}</p>
          ) : (
            <>
              <p className="m-0 text-sm text-text-2">{t('llm.acceptHint')}</p>
              <Button
                size="sm"
                className="max-sm:min-h-11"
                variant="secondary"
                loading={acceptLlm.isPending}
                onClick={() => acceptLlm.mutate(ad.id, { onSuccess: () => setAccepted(true) })}
              >
                {t('llm.accept')}
              </Button>
            </>
          )}
        </div>
      )}
    </section>
  );
}
