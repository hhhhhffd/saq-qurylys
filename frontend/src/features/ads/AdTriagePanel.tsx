import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useTriageAd } from '@/api/hooks/ads';
import type { AdReviewState, AdRow } from '@/api/types';
import { Chip } from '@/components/Chip';
import { SelectInput } from '@/components/form/SelectInput';
import { TextArea } from '@/components/form/TextArea';
import { Button } from '@/components/ui/button';
import { useEnum, useEnumOptions } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { AD_REVIEW_STATES, parseReviewState } from './constants';
import { REVIEW_TONE } from './reviewTone';

interface FormProps {
  ad: AdRow;
}

function TriageForm({ ad }: FormProps) {
  const { t } = useTranslation('ads');
  const options = useEnumOptions();
  const triage = useTriageAd();
  const [state, setState] = useState<AdReviewState>(ad.review_state);
  const [note, setNote] = useState(ad.review_note ?? '');
  const dirty = state !== ad.review_state || note.trim() !== (ad.review_note ?? '');

  return (
    <div className="flex flex-col gap-2.5">
      <SelectInput
        label={t('triage.state')}
        data={options('ad_review_state', AD_REVIEW_STATES)}
        value={state}
        onChange={(value) => setState(parseReviewState(value) ?? state)}
      />
      <TextArea
        label={t('triage.note')}
        placeholder={t('triage.notePlaceholder')}
        maxLength={2000}
        minRows={2}
        value={note}
        onChange={(event) => setNote(event.currentTarget.value)}
      />
      <div>
        <Button
          size="sm"
          className="max-sm:min-h-11"
          disabled={!dirty}
          loading={triage.isPending}
          onClick={() => triage.mutate({ id: ad.id, data: { state, note: note.trim() || null } })}
        >
          {t('triage.save')}
        </Button>
      </div>
    </div>
  );
}

/** Staff decision on the publication: current state, who and when set it, and the note. */
export function AdTriagePanel({ ad, editable }: { ad: AdRow; editable: boolean }) {
  const { t } = useTranslation('ads');
  const e = useEnum();
  const f = useFormat();

  return (
    <div className="flex flex-col gap-2.5 border-t border-border pt-3">
      <strong className="text-sm">{t('triage.title')}</strong>
      <div className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1.5 text-sm">
        <Chip tone={REVIEW_TONE[ad.review_state]}>{e('ad_review_state', ad.review_state)}</Chip>
        {ad.reviewed_at !== null && (
          <span className="text-text-2">
            {f.dateTime(ad.reviewed_at)}
            {ad.reviewed_by !== null && ` · ${t('triage.reviewedBy', { id: ad.reviewed_by })}`}
          </span>
        )}
      </div>
      {!editable && ad.review_note && <p className="text-sm [overflow-wrap:anywhere]">{ad.review_note}</p>}
      {editable && <TriageForm key={`${ad.review_state}|${ad.review_note ?? ''}`} ad={ad} />}
    </div>
  );
}
