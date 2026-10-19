import { useEffect, useState, type ReactNode } from 'react';
import { IconTopologyStar3 } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, useLocation, useSearchParams } from 'react-router';
import { useObjectAssignments } from '@/api/hooks/assignments';
import { useScoreHistory } from '@/api/hooks/objects';
import { findFactor, readBreakdown, type ObjectDetail } from '@/api/types';
import { Panel } from '@/components/Panel';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { AssignmentsSection } from './AssignmentsSection';
import { BreakdownList } from './BreakdownList';
import { ComplaintsSection } from './ComplaintsSection';
import { DocumentsSection } from './DocumentsSection';
import { InspectionsSection } from './InspectionsSection';
import { KnownFacts } from './KnownFacts';
import { LinkedEntitiesSection } from './LinkedEntitiesSection';
import { ObjectFacts } from './ObjectFacts';
import { ObjectHeader } from './ObjectHeader';
import { ObjectReviewActions } from './ObjectReviewActions';
import { PassportSection } from './PassportSection';
import { ReadinessGap } from './ReadinessGap';
import { RiskPanel } from './RiskPanel';
import { ScoreHistory } from './ScoreHistory';
import { VisionSection } from './VisionSection';

const TABS = ['overview', 'passport', 'documents', 'progress', 'complaints', 'assignments', 'linked', 'history'] as const;
type Tab = (typeof TABS)[number];
const DEFAULT_TAB: Tab = 'overview';

const isTab = (value: string | null): value is Tab => TABS.includes(value as Tab);

/** The tab that holds the element a `#hash` points at (evidence links, "next step" anchors). */
function tabOfHash(hash: string): Tab | null {
  const id = hash.slice(1);
  if (id === 'risk' || id === 'next-step' || id === 'breakdown') return 'overview';
  if (id === 'passport' || id === 'facts') return 'passport';
  if (id === 'documents' || id.startsWith('doc-')) return 'documents';
  if (id === 'inspections' || id === 'vision' || id.startsWith('inspection-')) return 'progress';
  if (id === 'complaints' || id.startsWith('complaint-')) return 'complaints';
  if (id === 'assignments') return 'assignments';
  if (id === 'linked-entities') return 'linked';
  if (id === 'history') return 'history';
  return null;
}

function TabLabel({ children, count }: { children: ReactNode; count?: number }) {
  return (
    <>
      {children}
      {count !== undefined && <span className="font-normal tabular-nums">{count}</span>}
    </>
  );
}

export function ObjectCard({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('objects');
  const { t: tGraph } = useTranslation('graph');
  const [params, setParams] = useSearchParams();
  const { hash } = useLocation();
  const assignments = useObjectAssignments(object.id);
  // Loaded up front so the history is ready for the printed dossier.
  useScoreHistory(object.id);
  const [printing, setPrinting] = useState(false);

  const tab = isTab(params.get('tab')) ? (params.get('tab') as Tab) : DEFAULT_TAB;
  const selectTab = (next: Tab, replace = false) => {
    const nextParams = new URLSearchParams(params);
    if (next === DEFAULT_TAB) nextParams.delete('tab');
    else nextParams.set('tab', next);
    setParams(nextParams, { replace });
  };

  // Anchors point into tabs that may be inactive: open the right tab, then scroll to the element.
  useEffect(() => {
    const target = tabOfHash(hash);
    if (target && target !== tab) {
      const nextParams = new URLSearchParams(params);
      nextParams.set('tab', target);
      setParams(nextParams, { replace: true });
      return;
    }
    if (hash) document.getElementById(decodeURIComponent(hash.slice(1)))?.scrollIntoView();
    // Only a new hash (or the tab it switched to) should move the page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hash, tab]);

  // The dossier prints every tab, so the lazily shown history is mounted for printing too.
  useEffect(() => {
    const before = () => setPrinting(true);
    const after = () => setPrinting(false);
    window.addEventListener('beforeprint', before);
    window.addEventListener('afterprint', after);
    return () => {
      window.removeEventListener('beforeprint', before);
      window.removeEventListener('afterprint', after);
    };
  }, []);

  const mismatch = findFactor(readBreakdown(object.latest_score), 'r5_readiness_mismatch');
  // Inactive tabs stay mounted (anchors keep working) and are all shown on paper.
  const content = (value: Tab, children: ReactNode) => (
    <TabsContent value={value} forceMount className="flex min-w-0 flex-col gap-4 data-[state=inactive]:hidden print:flex!">
      {children}
    </TabsContent>
  );

  return (
    <div>
      <ObjectHeader object={object} />
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(16rem,20rem)]">
        <aside
          aria-label={t('card.facts.title')}
          className="flex min-w-0 flex-col gap-4 lg:sticky lg:top-[calc(var(--header-h)+16px)] lg:order-2 print:static"
        >
          {/* The next step stays in view on every tab: it is the one action the card leads to. */}
          <ObjectReviewActions object={object} />
          <ObjectFacts object={object} onShowAll={() => selectTab('passport')} />
        </aside>
        <Tabs value={tab} onValueChange={(value) => selectTab(value as Tab)} className="min-w-0 lg:order-1">
          <TabsList aria-label={t('card.tabs.label')} className="max-w-full overflow-x-auto" data-print="hide">
            <TabsTrigger value="overview" className="h-10">
              <TabLabel>{t('card.tabs.overview')}</TabLabel>
            </TabsTrigger>
            <TabsTrigger value="passport" className="h-10">
              <TabLabel>{t('card.tabs.passport')}</TabLabel>
            </TabsTrigger>
            <TabsTrigger value="documents" className="h-10">
              <TabLabel count={object.documents.length}>{t('card.tabs.documents')}</TabLabel>
            </TabsTrigger>
            <TabsTrigger value="progress" className="h-10">
              <TabLabel count={object.inspections.length}>{t('card.tabs.progress')}</TabLabel>
            </TabsTrigger>
            <TabsTrigger value="complaints" className="h-10">
              <TabLabel count={object.complaints.length}>{t('card.tabs.complaints')}</TabLabel>
            </TabsTrigger>
            <TabsTrigger value="assignments" className="h-10">
              <TabLabel count={assignments.data?.length}>{t('card.tabs.assignments')}</TabLabel>
            </TabsTrigger>
            <TabsTrigger value="linked" className="h-10">
              <TabLabel count={object.linked_entities.length}>{t('card.tabs.linked')}</TabLabel>
            </TabsTrigger>
            <TabsTrigger value="history" className="h-10">
              <TabLabel>{t('card.tabs.history')}</TabLabel>
            </TabsTrigger>
          </TabsList>

          {content(
            'overview',
            <>
              <KnownFacts object={object} />
              <RiskPanel object={object} />
              <BreakdownList score={object.latest_score} />
            </>,
          )}
          {content('passport', <PassportSection object={object} />)}
          {content('documents', <DocumentsSection object={object} />)}
          {content(
            'progress',
            <>
              <Panel className="[&_section]:mt-0 [&_section]:border-t-0 [&_section]:pt-0">
                <ReadinessGap
                  actual={object.readiness_actual_pct}
                  claimed={object.readiness_claimed_pct}
                  gap={object.readiness_gap_pp}
                  overstated={mismatch?.triggered ?? false}
                />
              </Panel>
              <InspectionsSection object={object} />
              <VisionSection object={object} />
            </>,
          )}
          {content('complaints', <ComplaintsSection object={object} />)}
          {content('assignments', <AssignmentsSection object={object} />)}
          {content('linked', <LinkedEntitiesSection object={object} />)}
          {tab === 'history' || printing
            ? content(
                'history',
                <>
                  <ScoreHistory objectId={object.id} />
                  <Button asChild variant="secondary" className="min-h-11 self-start" data-print="hide">
                    <Link to={`/graph?object_id=${object.id}`}>
                      <IconTopologyStar3 />
                      {tGraph('open')}
                    </Link>
                  </Button>
                </>,
              )
            : null}
        </Tabs>
      </div>
    </div>
  );
}
