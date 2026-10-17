import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { VisionConfig, VisionFinding, VisionSessionDetail } from '@/api/types';
import { Panel } from '@/components/Panel';
import { Button } from '@/components/ui/button';
import { FindingCard } from './FindingCard';

interface Props {
  session: VisionSessionDetail;
  config: VisionConfig;
  onShow: (finding: VisionFinding) => void;
}

/** Two separate blocks: outdoor advertising, and the organisation of the building site. */
export function FindingsPanels({ session, config, onShow }: Props) {
  const { t } = useTranslation('vision');
  const [onlyPending, setOnlyPending] = useState(false);
  const blocks = [
    { id: 'outdoor', title: t('findings.outdoor'), items: session.findings.filter((finding) => finding.category === 'outdoor_ad') },
    {
      id: 'site',
      title: t('findings.site'),
      items: session.findings.filter((finding) => finding.category !== 'outdoor_ad' && (!onlyPending || finding.review_state === 'pending')),
    },
  ];
  return (
    <>
      {blocks.map((block) => (
        <Panel
          key={block.id}
          title={block.title}
          id={`vision-findings-${block.id}`}
          actions={
            block.id === 'site' && (
              <div className="flex items-center gap-1.5 text-xs text-text-2" role="group" aria-label={t('finding.filterLabel')}>
                <span>{t('finding.filterLabel')}:</span>
                <Button size="xs" variant={onlyPending ? 'secondary' : 'default'} aria-pressed={!onlyPending} onClick={() => setOnlyPending(false)}>
                  {t('finding.filterAll')}
                </Button>
                <Button size="xs" variant={onlyPending ? 'default' : 'secondary'} aria-pressed={onlyPending} onClick={() => setOnlyPending(true)}>
                  {t('finding.filterPending')}
                </Button>
              </div>
            )
          }
        >
          {block.items.length === 0 ? (
            <p className="m-0 text-text-3">{t('findings.empty')}</p>
          ) : (
            <div className="flex flex-col gap-3">
              {block.items.map((finding) => (
                <FindingCard key={finding.id} finding={finding} session={session} config={config} onShow={onShow} />
              ))}
            </div>
          )}
        </Panel>
      ))}
    </>
  );
}
