import { Fragment, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { PhraseHit } from '@/api/types';
import { useEnum } from '@/i18n/useEnum';
import { cn } from '@/lib/utils';
import { hitSource } from '@/lib/hitSource';
import { buildSegments, splitOcr } from './segments';

const CLAMP_CHARS = 420;
const CLAMP_LINES = 6;

function markClass(hit: PhraseHit): string {
  switch (hitSource(hit)) {
    case 'rejected':
      return 'bg-transparent text-text-3 line-through';
    // An AI hypothesis nobody has accepted does not count yet: dashed outline instead of the solid marker.
    case 'ai_hypothesis':
      return 'bg-transparent outline-[1.5px] outline-offset-1 outline-text-3 outline-dashed';
    case 'confirmed':
      return 'bg-zone-green-bg shadow-[inset_0_-2px_0_var(--zone-green)]';
    case 'dictionary':
      return 'bg-zone-yellow-bg shadow-[inset_0_-2px_0_var(--zone-yellow)]';
  }
}

interface Props {
  text: string;
  hits: PhraseHit[];
  /** the hit a risk-factor evidence link points to: drawn stronger than the rest */
  focusHitId?: number | null;
}

/** One piece of text with phrase hits marked by their character offsets; long texts are clamped. */
function TextBlock({ text, hits, focusHitId = null }: Props) {
  const { t } = useTranslation('ads');
  const e = useEnum();
  const [toggled, setToggled] = useState(false);
  const textId = useId();
  // The phrase a link points to must not be hidden by the clamp.
  const expanded = toggled || (focusHitId !== null && hits.some((hit) => hit.id === focusHitId));
  const long = text.length > CLAMP_CHARS || text.split('\n').length > CLAMP_LINES;

  return (
    <div>
      <p
        id={textId}
        className={cn(
          'm-0 font-sans text-sm leading-relaxed [overflow-wrap:anywhere] whitespace-pre-wrap',
          long && !expanded && 'line-clamp-6',
        )}
      >
        {buildSegments(text, hits).map((segment, index) =>
          segment.hit ? (
            <mark
              key={index}
              data-testid="phrase-mark"
              className={cn(
                'rounded-[3px] px-px text-inherit',
                markClass(segment.hit),
                segment.hit.id === focusHitId && 'outline-2 outline-offset-1 outline-zone-red',
              )}
              title={`${e('phrase_category', segment.hit.category)} · ${e('hit_source', hitSource(segment.hit))}`}
            >
              {segment.text}
            </mark>
          ) : (
            <Fragment key={index}>{segment.text}</Fragment>
          ),
        )}
      </p>
      {long && (
        <button
          type="button"
          className="mt-1 cursor-pointer text-sm text-link underline decoration-link/35 underline-offset-2 hover:decoration-current"
          aria-expanded={expanded}
          aria-controls={textId}
          onClick={() => setToggled(!expanded)}
        >
          {expanded ? t('text.collapse') : t('text.expand')}
        </button>
      )}
    </div>
  );
}

/** Ad text; the part recognised on the photos (SPEC 10.2) is a separate block, hits are marked in both parts. */
export function HighlightedText({ text, hits, focusHitId = null }: Props) {
  const { t } = useTranslation('ads');
  const { own, ocr } = splitOcr(text, hits);
  const showOcr = ocr !== null && ocr.text.trim() !== '';

  return (
    <div className="flex flex-col gap-2.5">
      {(!showOcr || own.text.trim() !== '') && <TextBlock text={own.text} hits={own.hits} focusHitId={focusHitId} />}
      {showOcr && (
        <section className="flex flex-col gap-1.5 rounded border border-border bg-surface-sunken px-3 py-2.5">
          <span className="text-2xs font-bold tracking-wider text-text-3 uppercase">{t('text.ocr')}</span>
          <TextBlock text={ocr.text} hits={ocr.hits} focusHitId={focusHitId} />
        </section>
      )}
    </div>
  );
}
