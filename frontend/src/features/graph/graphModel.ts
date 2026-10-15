import type { GraphFinding, LinkGraph } from '@/api/types';

/** Node id to the ids of the nodes it is joined to by an edge. */
export type Adjacency = Map<string, Set<string>>;

export function buildAdjacency(graph: LinkGraph): Adjacency {
  const adjacency: Adjacency = new Map(graph.nodes.map((node) => [node.id, new Set<string>()]));
  for (const edge of graph.edges) {
    adjacency.get(edge.source)?.add(edge.target);
    adjacency.get(edge.target)?.add(edge.source);
  }
  return adjacency;
}

function kindOf(nodeId: string): string {
  return nodeId.slice(0, nodeId.indexOf(':'));
}

/** Id of the phone or account node a finding is about. */
export function findingNodeId(finding: GraphFinding): string {
  return `${finding.kind === 'shared_phone' ? 'phone' : 'account'}:${finding.value}`;
}

/** A phone or an account with everything that uses it: neighbours, and the objects behind publications that name it. */
export function withHolders(adjacency: Adjacency, nodeId: string): Set<string> {
  const nodes = new Set([nodeId]);
  for (const near of adjacency.get(nodeId) ?? []) {
    nodes.add(near);
    if (kindOf(near) !== 'ad') continue;
    for (const other of adjacency.get(near) ?? []) {
      if (kindOf(other) === 'object') nodes.add(other);
    }
  }
  return nodes;
}

/** The nodes that make up a finding: the shared phone or account, its holders, their developers and objects. */
export function findingNodes(finding: GraphFinding, adjacency: Adjacency): Set<string> {
  const nodes = withHolders(adjacency, findingNodeId(finding));
  for (const id of finding.developer_ids) nodes.add(`developer:${id}`);
  for (const id of finding.object_ids) nodes.add(`object:${id}`);
  return new Set([...nodes].filter((id) => adjacency.has(id)));
}

const PHONE = /^\+7(\d{3})(\d{3})(\d{2})(\d{2})$/;

/** `+77000002001` as `+7 700 000 20 01`; anything else as it is. */
export function formatPhone(phone: string): string {
  const match = PHONE.exec(phone);
  return match ? `+7 ${match[1]} ${match[2]} ${match[3]} ${match[4]}` : phone;
}
