import { useTranslation } from 'react-i18next';
import type { VisionConfig, VisionFinding, VisionSessionDetail } from '@/api/types';
import { Panel } from '@/components/Panel';
import { FindingCard } from './FindingCard';

interface Props {
  session: VisionSessionDetail;
  config: VisionConfig;
  onShow: (finding: VisionFinding) => void;
}

/** Two separate blocks: outdoor advertising, and the organisation of the building site. */
export function FindingsPanels({ session, config, onShow }: Props) {
  const { t } = useTranslation('vision');
  const blocks = [
    { id: 'outdoor', title: t('findings.outdoor'), items: session.findings.filter((finding) => finding.category === 'outdoor_ad') },
    { id: 'site', title: t('findings.site'), items: session.findings.filter((finding) => finding.category !== 'outdoor_ad') },
  ];
  return (
    <>
      {blocks.map((block) => (
        <Panel key={block.id} title={block.title} id={`vision-findings-${block.id}`}>
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
