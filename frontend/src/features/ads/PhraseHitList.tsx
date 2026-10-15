import { Button } from '@mantine/core';
import { IconCheck } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useConfirmHit } from '@/api/hooks/ads';
import type { PhraseHit } from '@/api/types';
import { Chip } from '@/components/Chip';
import { useEnum } from '@/i18n/useEnum';
import { hitState } from './segments';
import classes from './PhraseHitList.module.css';

function HitState({ hit }: { hit: PhraseHit }) {
  const { t } = useTranslation('ads');
  const state = hitState(hit);
  if (state === 'confirmed') {
    return (
      <Chip tone="green">
        <IconCheck size={12} stroke={2.4} aria-hidden />
        {t('hits.confirmed')}
      </Chip>
    );
  }
  if (state === 'rejected') return <Chip>{t('hits.rejected')}</Chip>;
  if (hit.detected_by === 'llm') {
    return (
      <Chip tone="yellow" title={t('hits.llmUnreviewedHint')}>
        {t('hits.llmUnreviewed')}
      </Chip>
    );
  }
  return <span className={classes.unreviewed}>{t('hits.unreviewed')}</span>;
}

interface Props {
  adId: number;
  hits: PhraseHit[];
  editable: boolean;
}

export function PhraseHitList({ adId, hits, editable }: Props) {
  const { t } = useTranslation('ads');
  const e = useEnum();
  const confirmHit = useConfirmHit();
  const sorted = [...hits].sort((a, b) => a.start - b.start || a.id - b.id);
  const pending = confirmHit.isPending ? confirmHit.variables : undefined;

  return (
    <ul className={classes.list} aria-label={t('hits.title')}>
      {sorted.map((hit) => (
        <li key={hit.id} className={`${classes.hit} ${hit.confirmed === false ? classes.rejected : ''}`}>
          <div className={classes.main}>
            <span className={classes.matched}>«{hit.matched_text}»</span>
            <span className={classes.meta}>
              <span>{e('phrase_category', hit.category)}</span>
              <span className="tnum">{t('hits.weight', { weight: hit.weight })}</span>
              {hit.detected_by === 'llm' ? <Chip outline>{e('detected_by', 'llm')}</Chip> : <span>{e('detected_by', 'dictionary')}</span>}
            </span>
          </div>
          <div className={classes.state}>
            <HitState hit={hit} />
          </div>
          {editable && (
            <div className={classes.actions}>
              <Button
                size="compact-xs"
                variant="default"
                disabled={hit.confirmed === true}
                loading={pending?.hitId === hit.id && pending.confirmed}
                onClick={() => confirmHit.mutate({ adId, hitId: hit.id, confirmed: true })}
              >
                {t('confirm', { ns: 'common' })}
              </Button>
              <Button
                size="compact-xs"
                variant="default"
                disabled={hit.confirmed === false}
                loading={pending?.hitId === hit.id && !pending.confirmed}
                onClick={() => confirmHit.mutate({ adId, hitId: hit.id, confirmed: false })}
              >
                {t('hits.reject')}
              </Button>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
