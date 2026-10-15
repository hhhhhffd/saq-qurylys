import { useTranslation } from 'react-i18next';
import type { CollectorStatus } from '@/api/types';
import { Chip } from '@/components/Chip';
import { COLLECTOR_SOURCES, isCollectorOn } from './collectors';

/** State of every collector. They are switched on in the server's `.env`, so this is read-only. */
export function CollectorBadges({ collectors }: { collectors: CollectorStatus[] }) {
  const { t } = useTranslation('sources');
  return (
    <ul className="m-0 flex list-none flex-wrap gap-x-6 gap-y-2 p-0">
      {COLLECTOR_SOURCES.map((source) => {
        const on = isCollectorOn(source, collectors);
        return (
          <li key={source} className="flex items-center gap-2 text-sm">
            <strong className="font-semibold">{t(`collectors.names.${source}`)}</strong>
            <Chip tone={on ? 'green' : 'neutral'}>{on ? t('collectors.on') : t('collectors.off')}</Chip>
          </li>
        );
      })}
    </ul>
  );
}
