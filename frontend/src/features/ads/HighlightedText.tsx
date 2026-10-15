import { Fragment, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { PhraseHit } from '@/api/types';
import { useEnum } from '@/i18n/useEnum';
import { hitSource } from '@/lib/hitSource';
import { buildSegments, splitOcr } from './segments';
import classes from './HighlightedText.module.css';

const CLAMP_CHARS = 420;
const CLAMP_LINES = 6;

function markClass(hit: PhraseHit): string {
  switch (hitSource(hit)) {
    case 'rejected':
      return classes.rejected;
    // An AI hypothesis nobody has accepted does not count yet: dashed outline instead of the solid marker.
    case 'ai_hypothesis':
      return classes.assumption;
    case 'confirmed':
      return classes.confirmed;
    case 'dictionary':
      return classes.solid;
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
      <p id={textId} className={`${classes.text} ${long && !expanded ? classes.clamped : ''}`}>
        {buildSegments(text, hits).map((segment, index) =>
          segment.hit ? (
            <mark
              key={index}
              className={`${classes.mark} ${markClass(segment.hit)} ${segment.hit.id === focusHitId ? classes.focus : ''}`}
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
          className={classes.toggle}
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
    <div className={classes.parts}>
      {(!showOcr || own.text.trim() !== '') && <TextBlock text={own.text} hits={own.hits} focusHitId={focusHitId} />}
      {showOcr && (
        <section className={classes.ocr}>
          <span className={classes.ocrCaption}>{t('text.ocr')}</span>
          <TextBlock text={ocr.text} hits={ocr.hits} focusHitId={focusHitId} />
        </section>
      )}
    </div>
  );
}
