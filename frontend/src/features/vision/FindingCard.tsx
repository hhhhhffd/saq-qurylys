import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useReviewFinding } from '@/api/hooks/vision';
import type { FindingReviewAction, FindingStatus, VisionConfig, VisionFinding, VisionSessionDetail } from '@/api/types';
import { Chip } from '@/components/Chip';
import { SelectInput } from '@/components/form/SelectInput';
import { TextInput } from '@/components/form/TextInput';
import { Button } from '@/components/ui/button';
import { useEnum, useEnumOptions } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { confidenceLevel } from '@/lib/confidenceLevel';
import { FINDING_STATUSES, FINDING_STATUS_TONE, REVIEW_STATE_TONE, isFindingStatus } from './constants';
import { FindingCrop } from './FindingCrop';
import { OutdoorAdBox } from './OutdoorAdBox';

interface Props {
  finding: VisionFinding;
  session: VisionSessionDetail;
  config: VisionConfig;
  onShow: (finding: VisionFinding) => void;
}

const DECISIONS: { action: FindingReviewAction; variant: 'default' | 'secondary' | 'destructive' }[] = [
  { action: 'confirm', variant: 'default' },
  { action: 'reject', variant: 'secondary' },
  { action: 'needs_more_evidence', variant: 'secondary' },
  { action: 'not_applicable', variant: 'secondary' },
];

export function FindingCard({ finding, session, config, onShow }: Props) {
  const { t } = useTranslation('vision');
  const e = useEnum();
  const options = useEnumOptions();
  const f = useFormat();
  const review = useReviewFinding();
  const [comment, setComment] = useState('');
  // the status is sent with the decision only when the reviewer changed it
  const [status, setStatus] = useState<FindingStatus>(finding.status);
  const trimmed = comment.trim();

  const send = (action: FindingReviewAction) =>
    review.mutate(
      { id: finding.id, action, comment: trimmed || undefined, status: status !== finding.status ? status : undefined },
      { onSuccess: () => setComment('') },
    );

  return (
    <article
      className="flex min-w-0 flex-col gap-3 rounded border border-border bg-surface p-3"
      aria-label={t('finding.label', { id: finding.id })}
      data-testid="vision-finding"
    >
      <div className="flex flex-wrap items-start gap-3">
        <FindingCrop finding={finding} />
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-1.5">
            <strong className="text-sm">{e('vision_category', finding.category)}</strong>
            <Chip tone={FINDING_STATUS_TONE[finding.status]}>
              {finding.category === 'debris' && finding.status === 'possible_noncompliance'
                ? t('finding.debrisPossible')
                : e('vision_finding_status', finding.status)}
            </Chip>
            <Chip tone={REVIEW_STATE_TONE[finding.review_state]}>{e('vision_review_state', finding.review_state)}</Chip>
          </div>
          <p className="m-0 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-text-3">
            {finding.origin === 'manual' ? (
              t('finding.originManual', { name: finding.created_by_name ?? '—' })
            ) : (
              <>
                <Chip tone="info">
                  {finding.confidence !== null
                    ? t('finding.originModelBadge', { level: e('confidence_level', confidenceLevel(finding.confidence)) })
                    : t('finding.originModelBadgePlain')}
                </Chip>
                <span className="[overflow-wrap:anywhere]">{t('finding.modelVersion', { model: finding.model_version ?? '—' })}</span>
              </>
            )}
            {' · '}
            <span className="tabular-nums">{f.dateTime(finding.created_at)}</span>
          </p>
          {finding.note && <p className="m-0 text-sm text-text-2 [overflow-wrap:anywhere]">{finding.note}</p>}
          {finding.frame_id !== null && (
            <div>
              <Button size="xs" variant="secondary" onClick={() => onShow(finding)}>
                {t('finding.show')}
              </Button>
            </div>
          )}
        </div>
      </div>

      {finding.category === 'outdoor_ad' && <OutdoorAdBox finding={finding} session={session} config={config} />}

      <div className="flex flex-col gap-2">
        <TextInput
          label={t('finding.comment')}
          placeholder={t('finding.commentPlaceholder')}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
        />
        <SelectInput
          label={t('finding.changeStatus')}
          data={options('vision_finding_status', FINDING_STATUSES)}
          value={status}
          onChange={(value) => isFindingStatus(value) && setStatus(value)}
        />
        <div className="flex flex-wrap gap-2">
          {DECISIONS.map(({ action, variant }) => (
            <Button
              key={action}
              size="sm"
              variant={variant}
              disabled={action === 'not_applicable' && trimmed === ''}
              loading={review.isPending && review.variables?.id === finding.id && review.variables.action === action}
              onClick={() => send(action)}
            >
              {t(`finding.actions.${action}`)}
            </Button>
          ))}
          <Button size="sm" variant="ghost" disabled={trimmed === ''} onClick={() => send('comment')}>
            {t('finding.actions.comment')}
          </Button>
        </div>
        {trimmed === '' && <span className="text-xs text-text-3">{t('finding.notApplicableHint')}</span>}
      </div>

      {finding.reviews.length > 0 && (
        <section aria-label={t('finding.history')}>
          <h4 className="m-0 mb-1 text-2xs font-bold tracking-wider text-text-3 uppercase">{t('finding.history')}</h4>
          <ul className="flex flex-col gap-1 text-xs text-text-2">
            {finding.reviews.map((item) => (
              <li key={item.id}>
                <span className="tabular-nums">{f.dateTime(item.created_at)}</span> · {item.reviewer_name ?? '—'} ·{' '}
                <strong>{e('vision_review_action', item.action)}</strong>
                {item.comment && <span className="[overflow-wrap:anywhere]">: {item.comment}</span>}
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}
