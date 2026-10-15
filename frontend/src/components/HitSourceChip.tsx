import { useTranslation } from 'react-i18next';
import type { DetectedBy } from '@/api/types';
import { Chip, type ChipTone } from '@/components/Chip';
import { useEnum } from '@/i18n/useEnum';
import { hitSource, type HitSource } from '@/lib/hitSource';

const TONE: Record<HitSource, ChipTone> = {
  dictionary: 'neutral',
  ai_hypothesis: 'yellow',
  confirmed: 'green',
  rejected: 'neutral',
};

interface Props {
  hit: {
    detected_by: DetectedBy;
    confirmed: boolean | null;
    confidence?: number | null;
    uncertain?: boolean;
  };
}

/** Where a phrase hit comes from (D18): «Словарь» is a rule, «Гипотеза ИИ» is unconfirmed, «Подтверждено» is an analyst's decision. */
export function HitSourceChip({ hit }: Props) {
  const { t } = useTranslation('ads');
  const e = useEnum();
  const source = hitSource(hit);
  const confidence = hit.detected_by === 'llm' && hit.confidence != null ? Math.round(hit.confidence * 100) : null;

  return (
    <>
      <Chip
        tone={TONE[source]}
        outline={source === 'ai_hypothesis'}
        title={source === 'ai_hypothesis' ? t('hits.llmUnreviewedHint') : undefined}
      >
        {e('hit_source', source)}
        {confidence !== null && <span className="tabular-nums">{`· ${confidence}%`}</span>}
      </Chip>
      {hit.uncertain && source === 'ai_hypothesis' && <Chip tone="red">{t('hits.uncertain')}</Chip>}
    </>
  );
}
