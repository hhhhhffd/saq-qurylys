import { useState } from 'react';
import { IconScan } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { usePublishAd, useRunOcr } from '@/api/hooks/vision';
import type { VisionConfig, VisionFinding, VisionSessionDetail } from '@/api/types';
import { TextArea } from '@/components/form/TextArea';
import { ObjectSelect } from '@/components/ObjectSelect';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';

interface Props {
  finding: VisionFinding;
  session: VisionSessionDetail;
  config: VisionConfig;
}

/** OCR of the marked area, the analyst's own wording of the text, and the step into the ads feed. */
export function OutdoorAdBox({ finding, session, config }: Props) {
  const { t } = useTranslation('vision');
  const runOcr = useRunOcr();
  const publish = usePublishAd();
  const [draft, setDraft] = useState<string | null>(null);
  const [objectId, setObjectId] = useState<number | null>(session.object?.id ?? null);

  const text = draft ?? finding.confirmed_text ?? finding.ocr_text ?? '';
  const pending = finding.ocr_status === 'pending';
  const confirmed = finding.review_state === 'confirmed';
  const notApplicable = finding.status === 'not_applicable';
  const canOcr = config.ocr_enabled && finding.bbox !== null && finding.frame_id !== null;

  return (
    <div className="flex flex-col gap-3 rounded border border-border bg-surface-sunken p-3">
      <div className="flex flex-wrap items-center gap-2">
        {canOcr && !pending && (
          <Button size="sm" variant="secondary" loading={runOcr.isPending} onClick={() => runOcr.mutate(finding.id)}>
            <IconScan />
            {finding.ocr_status === null ? t('ocr.run') : t('ocr.rerun')}
          </Button>
        )}
        {pending && (
          <span className="inline-flex items-center gap-2 text-sm text-text-2" role="status">
            <Spinner role="presentation" aria-hidden className="size-3.5" />
            {t('ocr.pending')}
          </span>
        )}
        {!config.ocr_enabled && <span className="text-sm text-text-3">{t('ocr.disabled')}</span>}
        {config.ocr_enabled && finding.bbox === null && <span className="text-sm text-text-3">{t('ocr.needsBox')}</span>}
      </div>

      {finding.ocr_status === 'failed' && <p className="m-0 text-sm text-zone-red-ink">{t('ocr.failed')}</p>}
      {finding.ocr_status === 'done' && (
        <div className="text-sm" data-testid="vision-ocr-result">
          <p className="m-0 text-xs text-text-3">
            {t('ocr.rawLabel')}
            {finding.ocr_confidence !== null && ` · ${t('ocr.confidence', { value: Math.round(finding.ocr_confidence * 100) })}`}
            {finding.ocr_engine && ` · ${finding.ocr_engine}`}
          </p>
          <blockquote className="m-0 mt-1 border-l-2 border-border-strong pl-2 whitespace-pre-wrap text-text-2 [overflow-wrap:anywhere]">
            {finding.ocr_text || t('ocr.noText')}
          </blockquote>
        </div>
      )}

      {finding.ad_post_id !== null ? (
        <Link to={`/ads?ad=${finding.ad_post_id}`} className="text-sm font-semibold text-link hover:underline">
          {t('publish.open', { id: finding.ad_post_id })}
        </Link>
      ) : (
        <>
          <TextArea
            label={t('publish.text')}
            description={t('publish.textHint')}
            minRows={2}
            maxRows={6}
            value={text}
            onChange={(event) => setDraft(event.target.value)}
          />
          <ObjectSelect label={t('publish.object')} placeholder={t('publish.objectPlaceholder')} value={objectId} onChange={setObjectId} />
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              disabled={!confirmed || notApplicable || text.trim() === ''}
              loading={publish.isPending}
              onClick={() => publish.mutate({ id: finding.id, text: text.trim(), object_id: objectId })}
            >
              {t('publish.create')}
            </Button>
            {notApplicable ? (
              <span className="text-xs text-text-3">{t('publish.notApplicable')}</span>
            ) : (
              !confirmed && <span className="text-xs text-text-3">{t('publish.needsConfirm')}</span>
            )}
          </div>
        </>
      )}
    </div>
  );
}
