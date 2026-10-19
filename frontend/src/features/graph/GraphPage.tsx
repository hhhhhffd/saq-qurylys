import { useCallback, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useLinkGraph } from '@/api/hooks/graph';
import type { GraphNode, LinkGraph } from '@/api/types';
import { Button } from '@/components/ui/button';
import { EmptyState, QueryBoundary } from '@/components/QueryState';
import { PageHeader } from '@/components/PageHeader';
import { ZoneDisclaimer } from '@/components/ZoneDisclaimer';
import { parseId } from '@/features/objects/list/filters';
import { FindingsPanel } from './FindingsPanel';
import { Legend } from './Legend';
import { LinkGraphCanvas } from './LinkGraphCanvas';
import { SuggestionsPanel } from './SuggestionsPanel';
import { buildAdjacency, findingNodes, withHolders } from './graphModel';

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
            <Button variant="secondary" onClick={() => setParams({})}>
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

  const stats = useMemo(() => {
    const count = (type: GraphNode['type']) => graph.nodes.filter((node) => node.type === type).length;
    return [
      { key: 'objects', value: count('object') },
      { key: 'developers', value: count('developer') },
      { key: 'phones', value: count('phone') },
      { key: 'accounts', value: count('account') },
      { key: 'findings', value: graph.findings.length },
    ] as const;
  }, [graph]);

  return (
    <div className="flex flex-col gap-3.5 transition-opacity duration-(--dur) data-stale:opacity-60" data-stale={stale || undefined}>
      <div className="grid grid-cols-2 gap-2 md:grid-cols-5 md:gap-3" role="group" aria-label={t('stats.label')}>
        {stats.map(({ key, value }) => (
          <div key={key} className="flex flex-col gap-0.5 rounded border border-border bg-surface px-3 py-2">
            <span className="font-heading text-2xl leading-tight font-bold tabular-nums">{value}</span>
            <span className="text-xs font-semibold tracking-wide text-text-2">{t(`stats.${key}`)}</span>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-4 [--graph-h:auto] lg:h-(--graph-h) lg:grid-cols-[minmax(0,1fr)_380px] lg:[--graph-h:max(520px,calc(100dvh-20rem))]">
        <section
          className="flex h-[60dvh] min-h-[360px] min-w-0 flex-col overflow-hidden rounded border border-border bg-surface lg:h-auto"
          aria-label={t('title')}
        >
          {graph.nodes.length === 0 ? (
            <EmptyState>
              <strong>{t('empty')}</strong>
              <br />
              {t('emptyHint')}
            </EmptyState>
          ) : (
            <>
              <div className="min-h-0 flex-1">
                <LinkGraphCanvas
                  graph={graph}
                  highlight={highlight}
                  seedId={seedId}
                  onNodeClick={handleNodeClick}
                  onBackgroundClick={clearSelection}
                />
              </div>
              <div className="flex flex-col gap-2 border-t border-border px-3 py-2.5">
                <Legend />
                <p className="m-0 text-xs text-text-3">{t('canvas.hint')}</p>
                {graph.truncated && (
                  <p className="m-0 text-xs text-text-3" role="status">
                    {t('truncated', { count: graph.nodes.length })}
                  </p>
                )}
              </div>
            </>
          )}
        </section>
        <div className="flex min-h-0 min-w-0 flex-col gap-4 lg:overflow-y-auto">
          <FindingsPanel findings={graph.findings} nodes={graph.nodes} active={finding} onSelect={selectFinding} />
          <SuggestionsPanel />
        </div>
      </div>
    </div>
  );
}
