import { useState } from 'react';
import { IconChevronRight, IconTopologyStar3 } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import type { ObjectDetail } from '@/api/types';
import { Button } from '@/components/ui/button';
import { BreakdownList } from './BreakdownList';
import { ComplaintsSection } from './ComplaintsSection';
import { DocumentsSection } from './DocumentsSection';
import { InspectionsSection } from './InspectionsSection';
import { LinkedEntitiesSection } from './LinkedEntitiesSection';
import { ObjectHeader } from './ObjectHeader';
import { ObjectReviewActions } from './ObjectReviewActions';
import { PassportSection } from './PassportSection';
import { RiskPanel } from './RiskPanel';
import { ScoreHistory } from './ScoreHistory';

export function ObjectCard({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('objects');
  const { t: tGraph } = useTranslation('graph');
  const [detailsOpen, setDetailsOpen] = useState(false);

  return (
    <div>
      <ObjectHeader object={object} />
      <div className="mb-4 grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,24rem)]">
        <div className="order-2 min-w-0 lg:order-1">
          <RiskPanel object={object} />
        </div>
        <div className="order-1 min-w-0 lg:order-2">
          <ObjectReviewActions object={object} />
        </div>
      </div>
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <DocumentsSection object={object} />
          <InspectionsSection object={object} />
          <ComplaintsSection object={object} />
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <PassportSection object={object} />
          <LinkedEntitiesSection object={object} />
        </div>
      </div>
      <details
        className="mt-4 border-t border-border pt-2"
        onToggle={(event) => setDetailsOpen(event.currentTarget.open)}
      >
        <summary className="group flex min-h-11 cursor-pointer list-none items-center gap-2 font-medium text-text-2 hover:text-text focus-visible:rounded-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary [&::-webkit-details-marker]:hidden">
          <IconChevronRight
            size={16}
            className="transition-transform duration-(--dur) group-open:rotate-90"
            aria-hidden
          />
          {t('card.more.title')}
        </summary>
        {detailsOpen && (
          <div className="mt-3 grid items-start gap-4 lg:grid-cols-2">
            <BreakdownList score={object.latest_score} />
            <div className="flex min-w-0 flex-col gap-4">
              <ScoreHistory objectId={object.id} />
              <Button asChild variant="secondary" className="min-h-11 self-start">
                <Link to={`/graph?object_id=${object.id}`}>
                  <IconTopologyStar3 />
                  {tGraph('open')}
                </Link>
              </Button>
            </div>
          </div>
        )}
      </details>
    </div>
  );
}
