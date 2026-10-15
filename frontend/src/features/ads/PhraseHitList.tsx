import { useTranslation } from 'react-i18next';
import { useConfirmHit } from '@/api/hooks/ads';
import type { PhraseHit } from '@/api/types';
import { HitSourceChip } from '@/components/HitSourceChip';
import { Button } from '@/components/ui/button';
import { useEnum } from '@/i18n/useEnum';
import { hitSource } from '@/lib/hitSource';
import { cn } from '@/lib/utils';

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
    <ul className="m-0 flex list-none flex-col rounded border border-border bg-surface-raised p-0" aria-label={t('hits.title')}>
      {sorted.map((hit) => {
        const source = hitSource(hit);
        const hypothesis = hit.detected_by === 'llm';
        return (
          <li
            key={hit.id}
            id={`hit-${hit.id}`}
            className={cn(
              'grid grid-cols-1 items-center gap-x-3 gap-y-1.5 px-3 py-2 not-first:border-t not-first:border-border md:grid-cols-[minmax(0,1fr)_auto_auto]',
              hit.id === focusHitId && 'bg-zone-yellow-bg shadow-[inset_3px_0_0_var(--zone-yellow)]',
            )}
          >
            <div className="flex min-w-0 flex-col gap-0.5">
              <span
                className={cn(
                  'text-sm font-semibold [overflow-wrap:anywhere]',
                  hit.confirmed === false && 'font-normal text-text-3 line-through',
                )}
              >
                «{hit.matched_text}»
              </span>
              <span
                className={cn(
                  'flex flex-wrap items-center gap-x-2.5 gap-y-0.5 text-xs text-text-2',
                  hit.confirmed === false && 'opacity-70',
                )}
              >
                <span>{e('phrase_category', hit.category)}</span>
                <span className="tabular-nums">{t('hits.weight', { weight: hit.weight })}</span>
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-1 md:justify-end">
              <HitSourceChip hit={hit} />
            </div>
            {editable && (
              <div className="flex gap-1.5">
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={source === 'confirmed'}
                  loading={pending?.hitId === hit.id && pending.confirmed}
                  onClick={() => confirmHit.mutate({ adId, hitId: hit.id, confirmed: true })}
                >
                  {hypothesis ? t('hits.accept') : t('confirm', { ns: 'common' })}
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
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
