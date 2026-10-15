import { useTranslation } from 'react-i18next';
import type { CollectorStatus } from '@/api/types';
import { Chip } from '@/components/Chip';
import { COLLECTOR_SOURCES, isCollectorOn } from './collectors';
import classes from './SourcesPage.module.css';

/** State of every collector. They are switched on in the server's `.env`, so this is read-only. */
export function CollectorBadges({ collectors }: { collectors: CollectorStatus[] }) {
  const { t } = useTranslation('sources');
  return (
    <ul className={classes.collectors}>
      {COLLECTOR_SOURCES.map((source) => {
        const on = isCollectorOn(source, collectors);
        return (
          <li key={source} className={classes.collector}>
            <strong>{t(`collectors.names.${source}`)}</strong>
            <Chip tone={on ? 'green' : 'neutral'}>{on ? t('collectors.on') : t('collectors.off')}</Chip>
          </li>
        );
      })}
    </ul>
  );
}
