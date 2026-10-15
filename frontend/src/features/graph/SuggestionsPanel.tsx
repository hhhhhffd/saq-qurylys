import { Button } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { useAcceptSuggestion, useDismissSuggestion, useSourceSuggestions } from '@/api/hooks/graph';
import type { SourceSuggestion } from '@/api/types';
import { Chip } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { QueryBoundary } from '@/components/QueryState';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import classes from './SuggestionsPanel.module.css';

export function SuggestionsPanel() {
  const { t } = useTranslation('graph');
  const e = useEnum();
  const { date } = useFormat();
  const suggestions = useSourceSuggestions();
  const accept = useAcceptSuggestion();
  const dismiss = useDismissSuggestion();

  const accepting = accept.isPending ? accept.variables : undefined;
  const dismissing = dismiss.isPending ? dismiss.variables : undefined;
  const isSame = (item: SourceSuggestion, other?: Pick<SourceSuggestion, 'platform' | 'handle'>) =>
    other?.platform === item.platform && other.handle === item.handle;

  return (
    <Panel title={t('suggestions.title')}>
      <p className={classes.hint}>{t('suggestions.hint')}</p>
      <QueryBoundary query={suggestions}>
        {(items) =>
          items.length === 0 ? (
            <p className={classes.empty}>{t('suggestions.empty')}</p>
          ) : (
            <ul className={classes.list}>
              {items.map((item) => (
                <li key={`${item.platform}:${item.handle}`} className={classes.item}>
                  <div className={classes.head}>
                    <a
                      className={classes.handle}
                      href={item.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      aria-label={t('suggestions.openProfile', { handle: item.handle })}
                    >
                      @{item.handle}
                    </a>
                    <Chip>{e('platform', item.platform)}</Chip>
                  </div>
                  <p className={classes.meta}>
                    {t('suggestions.posts', { count: item.posts_count })} · {t('suggestions.lastSeen', { value: date(item.last_seen_at) })}
                  </p>
                  <div className={classes.actions}>
                    <Button
                      size="compact-sm"
                      loading={isSame(item, accepting)}
                      disabled={isSame(item, dismissing)}
                      onClick={() => accept.mutate(item)}
                    >
                      {t('suggestions.accept')}
                    </Button>
                    <Button
                      size="compact-sm"
                      variant="default"
                      loading={isSame(item, dismissing)}
                      disabled={isSame(item, accepting)}
                      onClick={() => dismiss.mutate({ platform: item.platform, handle: item.handle })}
                    >
                      {t('suggestions.dismiss')}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )
        }
      </QueryBoundary>
    </Panel>
  );
}
