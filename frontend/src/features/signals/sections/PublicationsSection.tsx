import { Fragment } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import type { AdStatus, SignalSections } from '@/api/types';
import { Chip, type ChipTone } from '@/components/Chip';
import { DemoBadge } from '@/components/DemoBadge';
import { HitSourceChip } from '@/components/HitSourceChip';
import { Panel } from '@/components/Panel';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { EvidenceList } from './EvidenceList';
import classes from './Sections.module.css';

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
        <p className={classes.empty}>{t('sections.empty')}</p>
      ) : (
        <>
          <p className={classes.tableHint}>{t('publications.hitsNote')}</p>
          <div className={classes.scroll}>
            <table className={classes.table}>
              <thead>
                <tr>
                  <th>{t('publications.platform')}</th>
                  <th>{t('publications.link')}</th>
                  <th>{t('publications.publishedAt')}</th>
                  <th>{t('publications.capturedAt')}</th>
                  <th>{t('publications.status')}</th>
                  <th>{t('publications.evidence')}</th>
                  {showAdLinks && <th>{t('publications.registry')}</th>}
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const href = externalHref(item.url);
                  return (
                    <Fragment key={item.ad_post_id}>
                      <tr>
                        <td>
                          <span className={classes.demoRow}>
                            {e('platform', item.platform)}
                            {item.is_demo && <DemoBadge />}
                          </span>
                        </td>
                        <td>
                          {href ? (
                            <a
                              href={href}
                              target="_blank"
                              rel="noopener noreferrer"
                              className={classes.link}
                              title={href}
                            >
                              {item.url}
                            </a>
                          ) : (
                            (item.url ?? '—')
                          )}
                        </td>
                        <td className="tnum">{date(item.published_at)}</td>
                        <td className="tnum">{dateTime(item.captured_at)}</td>
                        <td>
                          <Chip tone={AD_TONE[item.status]}>{e('ad_status', item.status)}</Chip>
                        </td>
                        <td>
                          <EvidenceList ids={item.evidence_ids} />
                        </td>
                        {showAdLinks && (
                          <td>
                            <Link to={`/ads?ad=${item.ad_post_id}`}>{t('publications.openInRegistry')}</Link>
                          </td>
                        )}
                      </tr>
                      {item.hits.length > 0 && (
                        <tr className={classes.hitsRow}>
                          <td colSpan={showAdLinks ? 7 : 6}>
                            <ul className={classes.hits} aria-label={t('publications.hits')}>
                              {item.hits.map((hit) => (
                                <li key={hit.id}>
                                  <span>«{hit.fragment}»</span>
                                  <span className={classes.hitCategory}>{e('phrase_category', hit.category)}</span>
                                  <HitSourceChip hit={hit} />
                                </li>
                              ))}
                            </ul>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Panel>
  );
}
