import { useCallback, useEffect, useMemo, useRef } from 'react';
import { ActionIcon } from '@mantine/core';
import { useElementSize } from '@/lib/hooks';
import { IconArrowsMaximize } from '@tabler/icons-react';
import ForceGraph2D, { type ForceGraphMethods, type LinkObject, type NodeObject } from 'react-force-graph-2d';
import { useTranslation } from 'react-i18next';
import type { GraphEdge, GraphNode, GraphNodeType, LinkGraph } from '@/api/types';
import { prefersReducedMotion } from '@/features/map/mapStyle';
import { formatPhone } from './graphModel';
import { nodeFill, readGraphPalette, type GraphPalette } from './palette';
import classes from './LinkGraphCanvas.module.css';

/** The library replaces `source` and `target` of a link with the node objects, so the ids are not part of the type. */
type EdgeData = Omit<GraphEdge, 'source' | 'target'>;
type CanvasNode = NodeObject<GraphNode>;
type CanvasLink = LinkObject<GraphNode, EdgeData>;

/** Half-size of a node in graph units. Developers and objects are the large ones. */
const NODE_SIZE: Record<GraphNodeType, number> = { developer: 8, object: 8, phone: 6, account: 6, ad: 3.5 };
/** Zoom level from which the label of a node is always drawn. */
const LABEL_SCALE: Record<GraphNodeType, number> = { developer: 1.4, object: 1.4, phone: 1.8, account: 1.8, ad: 3 };
const DIMMED_ALPHA = 0.1;
const LABEL_FONT_PX = 12;
const LABEL_MAX_CHARS = 42;
const FIT_PADDING = 48;
const FOCUS_PADDING = 90;
const FIT_MS = 450;
const COOLDOWN_MS = 6000;
const COOLDOWN_REDUCED_MS = 1200;
const WARMUP_REDUCED_TICKS = 120;
const AD_EDGES = new Set<EdgeData['type']>(['ad_object', 'ad_phone', 'ad_account']);

function endId(end: CanvasLink['source']): string {
  return typeof end === 'object' ? String(end.id) : String(end);
}

function tracePath(ctx: CanvasRenderingContext2D, type: GraphNodeType, x: number, y: number, size: number) {
  switch (type) {
    case 'developer':
      ctx.roundRect(x - size, y - size, size * 2, size * 2, size * 0.3);
      break;
    case 'phone':
      ctx.moveTo(x, y - size);
      ctx.lineTo(x + size, y);
      ctx.lineTo(x, y + size);
      ctx.lineTo(x - size, y);
      ctx.closePath();
      break;
    case 'account':
      ctx.moveTo(x, y - size);
      ctx.lineTo(x + size * 0.95, y + size * 0.7);
      ctx.lineTo(x - size * 0.95, y + size * 0.7);
      ctx.closePath();
      break;
    default:
      ctx.arc(x, y, size, 0, Math.PI * 2);
  }
}

function drawLabel(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, scale: number, palette: GraphPalette) {
  const fontSize = LABEL_FONT_PX / scale;
  ctx.font = `${fontSize}px ${palette.font}`;
  const shown = text.length > LABEL_MAX_CHARS ? `${text.slice(0, LABEL_MAX_CHARS - 1)}…` : text;
  const width = ctx.measureText(shown).width;
  const pad = 3 / scale;
  ctx.globalAlpha = 0.92;
  ctx.fillStyle = palette.labelBackground;
  ctx.beginPath();
  ctx.roundRect(x - width / 2 - pad, y - pad / 2, width + pad * 2, fontSize + pad * 1.5, 3 / scale);
  ctx.fill();
  ctx.globalAlpha = 1;
  ctx.fillStyle = palette.text;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.fillText(shown, x, y + pad / 4);
}

interface Props {
  graph: LinkGraph;
  /** nodes to emphasise; the others are dimmed. null = no emphasis */
  highlight: Set<string> | null;
  /** the node the view was opened for */
  seedId: string | null;
  onNodeClick: (node: GraphNode) => void;
  onBackgroundClick: () => void;
}

export function LinkGraphCanvas({ graph, highlight, seedId, onNodeClick, onBackgroundClick }: Props) {
  const { t } = useTranslation('graph');
  const { ref, width, height } = useElementSize();
  const fgRef = useRef<ForceGraphMethods<GraphNode, EdgeData> | undefined>(undefined);
  const hoveredId = useRef<string | null>(null);
  const fitted = useRef(false);
  const previousHighlight = useRef<Set<string> | null>(null);
  const palette = useMemo(() => readGraphPalette(), []);
  const reducedMotion = useMemo(() => prefersReducedMotion(), []);
  const ready = width > 0 && height > 0;

  // The graph library writes positions into the objects it is given, so it gets its own copies.
  const graphData = useMemo(
    () => ({ nodes: graph.nodes.map((node) => ({ ...node })), links: graph.edges.map((edge) => ({ ...edge })) }),
    [graph],
  );

  useEffect(() => {
    fitted.current = false;
  }, [graphData]);

  useEffect(() => {
    if (!ready) return;
    // Repulsion with a limited reach keeps separate clusters from drifting far apart, which would shrink everything.
    fgRef.current?.d3Force('charge')?.strength(-70).distanceMax(160);
    fgRef.current?.d3Force('link')?.distance(40);
  }, [graphData, ready]);

  // Choosing a finding or a node brings the involved part into view; clearing the choice shows everything again.
  useEffect(() => {
    if (highlight === previousHighlight.current) return;
    previousHighlight.current = highlight;
    const duration = reducedMotion ? 0 : FIT_MS;
    if (highlight) fgRef.current?.zoomToFit(duration, FOCUS_PADDING, (node) => highlight.has(String(node.id)));
    else fgRef.current?.zoomToFit(duration, FIT_PADDING);
  }, [highlight, reducedMotion]);

  const handleEngineStop = useCallback(() => {
    // Also fires after a node is dragged; the view is only fitted once per set of data.
    if (fitted.current) return;
    fitted.current = true;
    fgRef.current?.zoomToFit(reducedMotion ? 0 : FIT_MS, FIT_PADDING);
  }, [reducedMotion]);

  const paintNode = useCallback(
    (node: CanvasNode, ctx: CanvasRenderingContext2D, scale: number) => {
      const x = node.x ?? 0;
      const y = node.y ?? 0;
      const involved = highlight?.has(node.id) === true;
      const dimmed = highlight !== null && !involved;
      const isSeed = node.id === seedId;
      const holder = node.type === 'phone' || node.type === 'account';
      const size = NODE_SIZE[node.type] * (isSeed ? 1.3 : 1) * (involved && holder ? 1.4 : 1);

      ctx.save();
      ctx.globalAlpha = dimmed ? DIMMED_ALPHA : 1;
      ctx.beginPath();
      tracePath(ctx, node.type, x, y, size);
      ctx.fillStyle = nodeFill(node, palette);
      ctx.fill();
      ctx.lineWidth = 1.2 / scale;
      ctx.strokeStyle = palette.outline;
      ctx.stroke();

      if (involved || isSeed) {
        ctx.beginPath();
        ctx.arc(x, y, size + 3.5 / scale + 1.5, 0, Math.PI * 2);
        ctx.lineWidth = (involved ? 2.2 : 1.4) / scale;
        ctx.strokeStyle = palette.ring;
        ctx.stroke();
      }

      const hovered = hoveredId.current === node.id;
      // Publications are many and their labels long: they are named on hover or when zoomed in, not when emphasised.
      const named = node.type !== 'ad' && (involved || isSeed);
      if (hovered || (!dimmed && (named || scale >= LABEL_SCALE[node.type]))) {
        ctx.globalAlpha = 1;
        const label = node.type === 'phone' ? formatPhone(node.label) : node.label;
        drawLabel(ctx, label, x, y + size + 3 / scale, scale, palette);
      }
      ctx.restore();
    },
    [highlight, seedId, palette],
  );

  const paintPointerArea = useCallback((node: CanvasNode, color: string, ctx: CanvasRenderingContext2D) => {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(node.x ?? 0, node.y ?? 0, NODE_SIZE[node.type] + 3, 0, Math.PI * 2);
    ctx.fill();
  }, []);

  const isLinkDimmed = useCallback(
    (link: CanvasLink) => highlight !== null && !(highlight.has(endId(link.source)) && highlight.has(endId(link.target))),
    [highlight],
  );

  return (
    <div
      ref={ref}
      className={classes.stage}
      role="group"
      aria-label={t('canvas.label', { nodes: graph.nodes.length, edges: graph.edges.length })}
    >
      {ready && (
        <ForceGraph2D<GraphNode, EdgeData>
          ref={fgRef}
          width={width}
          height={height}
          graphData={graphData}
          nodeId="id"
          nodeLabel={() => ''}
          nodeCanvasObject={paintNode}
          nodePointerAreaPaint={paintPointerArea}
          linkColor={(link: CanvasLink) =>
            highlight === null ? palette.edge : isLinkDimmed(link) ? palette.edgeFaint : palette.edgeStrong
          }
          linkWidth={(link: CanvasLink) => (highlight !== null && !isLinkDimmed(link) ? 2.2 : 1)}
          linkLineDash={(link: CanvasLink) => (AD_EDGES.has(link.type) ? [3, 3] : null)}
          // Highlighting changes only what the callbacks return, so the canvas has to keep redrawing.
          autoPauseRedraw={false}
          minZoom={0.2}
          maxZoom={8}
          cooldownTime={reducedMotion ? COOLDOWN_REDUCED_MS : COOLDOWN_MS}
          warmupTicks={reducedMotion ? WARMUP_REDUCED_TICKS : 0}
          onEngineStop={handleEngineStop}
          onNodeHover={(node) => {
            hoveredId.current = node ? String(node.id) : null;
          }}
          onNodeClick={(node) => onNodeClick(node)}
          onBackgroundClick={onBackgroundClick}
        />
      )}
      <ActionIcon
        className={classes.fit}
        variant="default"
        size="lg"
        aria-label={t('canvas.fit')}
        title={t('canvas.fit')}
        onClick={() => fgRef.current?.zoomToFit(reducedMotion ? 0 : FIT_MS, FIT_PADDING)}
      >
        <IconArrowsMaximize size={18} stroke={1.7} />
      </ActionIcon>
    </div>
  );
}
