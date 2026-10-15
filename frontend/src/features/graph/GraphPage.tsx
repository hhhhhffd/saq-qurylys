import { useCallback, useMemo, useState } from 'react';
import { Button } from '@mantine/core';
import { useNavigate, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useLinkGraph } from '@/api/hooks/graph';
import type { GraphNode, LinkGraph } from '@/api/types';
import { EmptyState, QueryBoundary } from '@/components/QueryState';
import { PageHeader } from '@/components/PageHeader';
import { ZoneDisclaimer } from '@/components/ZoneDisclaimer';
import { parseId } from '@/features/objects/list/filters';
import { FindingsPanel } from './FindingsPanel';
import { Legend } from './Legend';
import { LinkGraphCanvas } from './LinkGraphCanvas';
import { SuggestionsPanel } from './SuggestionsPanel';
import { buildAdjacency, findingNodes, withHolders } from './graphModel';
import classes from './GraphPage.module.css';

export function GraphPage() {
  const { t } = useTranslation('graph');
  const [params, setParams] = useSearchParams();
  const objectId = parseId(params.get('object_id'));
  const developerId = objectId === null ? parseId(params.get('developer_id')) : null;
  const seedId = objectId !== null ? `object:${objectId}` : developerId !== null ? `developer:${developerId}` : null;
  const graph = useLinkGraph({ object_id: objectId ?? undefined, developer_id: developerId ?? undefined });

  const seed = graph.data?.nodes.find((node) => node.id === seedId);
  const subtitle = seed ? t(`focus.${seed.type}`, { name: seed.label }) : t('subtitle');

  return (
    <>
      <PageHeader
        title={t('title')}
        subtitle={subtitle}
        actions={
          seedId !== null && (
            <Button variant="default" onClick={() => setParams({})}>
              {t('showAll')}
            </Button>
          )
        }
      />
      <ZoneDisclaimer />
      <QueryBoundary query={graph}>
        {(data) => (
          <GraphWorkspace
            key={seedId ?? 'all'}
            graph={data}
            seedId={seedId}
            stale={graph.isPlaceholderData}
            onRecentre={(id) => setParams({ developer_id: String(id) })}
          />
        )}
      </QueryBoundary>
    </>
  );
}

interface WorkspaceProps {
  graph: LinkGraph;
  seedId: string | null;
  /** showing the previous view while the new one loads */
  stale: boolean;
  onRecentre: (developerId: number) => void;
}

function GraphWorkspace({ graph, seedId, stale, onRecentre }: WorkspaceProps) {
  const { t } = useTranslation('graph');
  const navigate = useNavigate();
  const adjacency = useMemo(() => buildAdjacency(graph), [graph]);
  // One thing at a time is emphasised: a finding chosen in the list, or a phone/account chosen on the graph.
  const [finding, setFinding] = useState<number | null>(null);
  const [pickedId, setPickedId] = useState<string | null>(null);

  const highlight = useMemo(() => {
    const chosen = finding === null ? undefined : graph.findings[finding];
    if (chosen) return findingNodes(chosen, adjacency);
    return pickedId !== null && adjacency.has(pickedId) ? withHolders(adjacency, pickedId) : null;
  }, [finding, pickedId, graph.findings, adjacency]);

  const selectFinding = useCallback((index: number | null) => {
    setFinding(index);
    setPickedId(null);
  }, []);

  const clearSelection = useCallback(() => {
    setFinding(null);
    setPickedId(null);
  }, []);

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      switch (node.type) {
        case 'object':
          void navigate(`/objects/${node.ref_id}`);
          break;
        case 'ad':
          void navigate(`/ads?ad=${node.ref_id}`);
          break;
        case 'developer':
          if (node.id !== seedId && node.ref_id !== null) onRecentre(node.ref_id);
          break;
        default:
          setFinding(null);
          setPickedId((current) => (current === node.id ? null : node.id));
      }
    },
    [navigate, onRecentre, seedId],
  );

  return (
    <div className={classes.layout} data-stale={stale || undefined}>
      <section className={`panel ${classes.stage}`} aria-label={t('title')}>
        {graph.nodes.length === 0 ? (
          <EmptyState>
            <strong>{t('empty')}</strong>
            <br />
            {t('emptyHint')}
          </EmptyState>
        ) : (
          <>
            <LinkGraphCanvas
              graph={graph}
              highlight={highlight}
              seedId={seedId}
              onNodeClick={handleNodeClick}
              onBackgroundClick={clearSelection}
            />
            <div className={classes.footer}>
              <Legend />
              <p className={classes.note}>{t('canvas.hint')}</p>
              {graph.truncated && (
                <p className={classes.note} role="status">
                  {t('truncated', { count: graph.nodes.length })}
                </p>
              )}
            </div>
          </>
        )}
      </section>
      <div className={classes.side}>
        <FindingsPanel findings={graph.findings} nodes={graph.nodes} active={finding} onSelect={selectFinding} />
        <SuggestionsPanel />
      </div>
    </div>
  );
}
