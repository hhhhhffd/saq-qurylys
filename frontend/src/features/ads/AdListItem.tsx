import { useTranslation } from 'react-i18next';
import type { AdRow } from '@/api/types';
import { Chip } from '@/components/Chip';
import { DemoBadge } from '@/components/DemoBadge';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { cn } from '@/lib/utils';

interface Props {
  ad: AdRow;
  selected: boolean;
  onSelect: (id: number) => void;
}

/** One compact row of the master list; the full card opens beside it. */
export function AdListItem({ ad, selected, onSelect }: Props) {
  const { t } = useTranslation('ads');
  const e = useEnum();
  const f = useFormat();

  return (
    <li className="m-0">
      <button
        type="button"
        aria-current={selected ? 'true' : undefined}
        aria-label={t('list.open', { id: ad.id })}
        onClick={() => onSelect(ad.id)}
        className={cn(
          'flex w-full min-w-0 cursor-pointer flex-col gap-1.5 border-0 border-l-[3px] border-l-transparent bg-transparent px-3 py-2.5 text-left transition-colors duration-(--dur) hover:bg-surface-raised max-sm:min-h-11',
          selected && 'border-l-focus bg-surface-raised',
        )}
      >
        <span className="flex min-w-0 items-center justify-between gap-2">
          <span className="min-w-0 truncate text-sm font-bold">{ad.author ?? t('list.noAuthor')}</span>
          <span className="shrink-0 text-xs text-text-3 tabular-nums">{f.date(ad.published_at ?? ad.captured_at)}</span>
        </span>
        <span className="line-clamp-2 text-sm leading-5 text-text-2 [overflow-wrap:anywhere]">
          {ad.text || t('card.noText')}
        </span>
        <span className="flex min-w-0 flex-wrap items-center gap-1.5">
          <Chip>{e('platform', ad.platform)}</Chip>
          <Chip tone={ad.status === 'captured' ? 'green' : ad.status === 'verification' ? 'yellow' : 'neutral'}>
            {ad.status === 'verification' ? t('card.linkNeedsReview') : e('ad_status', ad.status)}
          </Chip>
          {ad.is_demo && <DemoBadge />}
        </span>
      </button>
    </li>
  );
}
