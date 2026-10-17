import type { ObjectDetail } from '@/api/types';
import { BreakdownList } from './BreakdownList';
import { ComplaintsSection } from './ComplaintsSection';
import { DocumentsSection } from './DocumentsSection';
import { InspectionsSection } from './InspectionsSection';
import { LinkedEntitiesSection } from './LinkedEntitiesSection';
import { ObjectHeader } from './ObjectHeader';
import { PassportSection } from './PassportSection';
import { RiskPanel } from './RiskPanel';
import { ScoreHistory } from './ScoreHistory';
import { VisionSection } from './VisionSection';

export function ObjectCard({ object }: { object: ObjectDetail }) {
  return (
    <div>
      <ObjectHeader object={object} />
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
        <div className="flex min-w-0 flex-col gap-4">
          <PassportSection object={object} />
          <DocumentsSection object={object} />
          <InspectionsSection object={object} />
          <VisionSection object={object} />
          <ComplaintsSection object={object} />
          <LinkedEntitiesSection object={object} />
        </div>
        <div className="flex min-w-0 flex-col gap-4">
          <RiskPanel object={object} />
          <BreakdownList score={object.latest_score} />
          <ScoreHistory objectId={object.id} />
        </div>
      </div>
    </div>
  );
}
