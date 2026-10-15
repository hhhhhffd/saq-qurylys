import { Fragment, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { PhraseHit } from '@/api/types';
import { useEnum } from '@/i18n/useEnum';
import { buildSegments, hitState } from './segments';
import classes from './HighlightedText.module.css';

const CLAMP_CHARS = 420;
const CLAMP_LINES = 6;

function markClass(hit: PhraseHit): string {
  const state = hitState(hit);
  if (state === 'rejected') return classes.rejected;
  // An unreviewed AI assumption does not count yet: dashed outline instead of the solid marker.
  if (state === 'unreviewed' && hit.detected_by === 'llm') return classes.assumption;
  return classes.solid;
}

interface Props {
  text: string;
  hits: PhraseHit[];
}

/** Ad text with phrase hits marked by their character offsets; long texts are clamped. */
export function HighlightedText({ text, hits }: Props) {
  const { t } = useTranslation('ads');
  const e = useEnum();
  const [expanded, setExpanded] = useState(false);
  const textId = useId();
  const long = text.length > CLAMP_CHARS || text.split('\n').length > CLAMP_LINES;

  return (
    <div>
      <p id={textId} className={`${classes.text} ${long && !expanded ? classes.clamped : ''}`}>
        {buildSegments(text, hits).map((segment, index) =>
          segment.hit ? (
            <mark
              key={index}
              className={`${classes.mark} ${markClass(segment.hit)}`}
              title={`${e('phrase_category', segment.hit.category)} · ${e('detected_by', segment.hit.detected_by)}`}
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
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? t('text.collapse') : t('text.expand')}
        </button>
      )}
    </div>
  );
}
