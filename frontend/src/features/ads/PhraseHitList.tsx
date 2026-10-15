import { Button } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { useConfirmHit } from '@/api/hooks/ads';
import type { PhraseHit } from '@/api/types';
import { HitSourceChip } from '@/components/HitSourceChip';
import { useEnum } from '@/i18n/useEnum';
import { hitSource } from '@/lib/hitSource';
import classes from './PhraseHitList.module.css';

interface Props {
  adId: number;
  hits: PhraseHit[];
  editable: boolean;
  /** the hit a risk-factor evidence link points to */
  focusHitId?: number | null;
}

export function PhraseHitList({ adId, hits, editable, focusHitId = null }: Props) {
  const { t } = useTranslation('ads');
  const e = useEnum();
  const confirmHit = useConfirmHit();
  const sorted = [...hits].sort((a, b) => a.start - b.start || a.id - b.id);
  const pending = confirmHit.isPending ? confirmHit.variables : undefined;

  return (
    <ul className={classes.list} aria-label={t('hits.title')}>
      {sorted.map((hit) => {
        const source = hitSource(hit);
        const hypothesis = hit.detected_by === 'llm';
        return (
          <li
            key={hit.id}
            id={`hit-${hit.id}`}
            className={`${classes.hit} ${hit.confirmed === false ? classes.rejected : ''} ${hit.id === focusHitId ? classes.focused : ''}`}
          >
            <div className={classes.main}>
              <span className={classes.matched}>«{hit.matched_text}»</span>
              <span className={classes.meta}>
                <span>{e('phrase_category', hit.category)}</span>
                <span className="tnum">{t('hits.weight', { weight: hit.weight })}</span>
              </span>
            </div>
            <div className={classes.state}>
              <HitSourceChip hit={hit} />
            </div>
            {editable && (
              <div className={classes.actions}>
                <Button
                  size="compact-xs"
                  variant="default"
                  disabled={source === 'confirmed'}
                  loading={pending?.hitId === hit.id && pending.confirmed}
                  onClick={() => confirmHit.mutate({ adId, hitId: hit.id, confirmed: true })}
                >
                  {hypothesis ? t('hits.accept') : t('confirm', { ns: 'common' })}
                </Button>
                <Button
                  size="compact-xs"
                  variant="default"
                  disabled={source === 'rejected'}
                  loading={pending?.hitId === hit.id && !pending.confirmed}
                  onClick={() => confirmHit.mutate({ adId, hitId: hit.id, confirmed: false })}
                >
                  {t('hits.reject')}
                </Button>
              </div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
