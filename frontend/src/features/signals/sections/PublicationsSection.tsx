import { Fragment } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import type { AdStatus, SignalSections } from '@/api/types';
import { Chip, type ChipTone } from '@/components/Chip';
import { HitSourceChip } from '@/components/HitSourceChip';
import { Panel } from '@/components/Panel';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { EvidenceList } from './EvidenceList';

const AD_TONE: Record<AdStatus, ChipTone> = {
  captured: 'neutral',
  verification: 'yellow',
  removed_saved: 'info',
};

/** Publication URLs come from the outside world: only http(s) links become clickable. */
function externalHref(url: string | null): string | null {
  if (!url) return null;
  try {
    const { protocol, href } = new URL(url);
    return protocol === 'http:' || protocol === 'https:' ? href : null;
  } catch {
    return null;
  }
}

interface Props {
  items: SignalSections['publications'];
  /** recipients cannot open the ads registry */
  showAdLinks: boolean;
}

export function PublicationsSection({ items, showAdLinks }: Props) {
  const { t } = useTranslation('signals');
  const e = useEnum();
  const { date, dateTime } = useFormat();
  return (
    <Panel title={t('sections.publications')} flush>
      {items.length === 0 ? (
        <p className="px-3 py-2.5 text-text-3">{t('sections.empty')}</p>
      ) : (
        <>
          <p className="px-3 py-2 text-xs text-text-3">{t('publications.hitsNote')}</p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('publications.platform')}</TableHead>
                <TableHead>{t('publications.link')}</TableHead>
                <TableHead>{t('publications.publishedAt')}</TableHead>
                <TableHead>{t('publications.capturedAt')}</TableHead>
                <TableHead>{t('publications.status')}</TableHead>
                <TableHead>{t('publications.evidence')}</TableHead>
                {showAdLinks && <TableHead>{t('publications.registry')}</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => {
                const href = externalHref(item.url);
                return (
                  <Fragment key={item.ad_post_id}>
                    <TableRow className={item.hits.length > 0 ? 'border-b-0' : undefined}>
                      <TableCell>
                        <span className="inline-flex items-center gap-1.5">
                          {e('platform', item.platform)}
                        </span>
                      </TableCell>
                      <TableCell>
                        {href ? (
                          <a
                            href={href}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-block max-w-64 truncate align-bottom text-link hover:underline"
                            title={href}
                          >
                            {item.url}
                          </a>
                        ) : (
                          (item.url ?? '—')
                        )}
                      </TableCell>
                      <TableCell className="tabular-nums">{date(item.published_at)}</TableCell>
                      <TableCell className="tabular-nums">{dateTime(item.captured_at)}</TableCell>
                      <TableCell>
                        <Chip tone={AD_TONE[item.status]}>{e('ad_status', item.status)}</Chip>
                      </TableCell>
                      <TableCell>
                        <EvidenceList ids={item.evidence_ids} />
                      </TableCell>
                      {showAdLinks && (
                        <TableCell>
                          <Link to={`/ads?ad=${item.ad_post_id}`} className="text-link hover:underline">
                            {t('publications.openInRegistry')}
                          </Link>
                        </TableCell>
                      )}
                    </TableRow>
                    {item.hits.length > 0 && (
                      <TableRow className="bg-surface-raised">
                        <TableCell colSpan={showAdLinks ? 7 : 6} className="h-auto pt-0">
                          <ul className="m-0 flex list-none flex-col gap-1 p-0" aria-label={t('publications.hits')}>
                            {item.hits.map((hit) => (
                              <li key={hit.id} className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
                                <span>«{hit.fragment}»</span>
                                <span className="text-xs text-text-3">{e('phrase_category', hit.category)}</span>
                                <HitSourceChip hit={hit} />
                              </li>
                            ))}
                          </ul>
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        </>
      )}
    </Panel>
  );
}
