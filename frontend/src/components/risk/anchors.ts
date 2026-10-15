export type AnchorType = 'document' | 'complaint' | 'inspection';

const PREFIX: Record<AnchorType, string> = { document: 'doc', complaint: 'complaint', inspection: 'inspection' };

/** DOM id of a registry row, so risk evidence links can jump to it. */
export function anchorId(type: AnchorType, id: number): string {
  return `${PREFIX[type]}-${id}`;
}

export function isAnchorType(type: string): type is AnchorType {
  return type in PREFIX;
}
