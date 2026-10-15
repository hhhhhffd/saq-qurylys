import type { GraphNode, Zone } from '@/api/types';
import { readToken } from '@/features/map/mapStyle';

/** Canvas cannot use CSS variables, so the theme tokens (theme/tokens.css) are resolved once to concrete colors. */
export interface GraphPalette {
  developer: string;
  phone: string;
  account: string;
  ad: string;
  zone: Record<Zone | 'none', string>;
  edge: string;
  edgeFaint: string;
  edgeStrong: string;
  ring: string;
  outline: string;
  text: string;
  labelBackground: string;
  font: string;
}

export function readGraphPalette(): GraphPalette {
  return {
    developer: readToken('--graph-developer'),
    // Muted tones: pink is kept for the selection ring, so a chosen node stands out.
    phone: readToken('--text-2'),
    account: readToken('--text-3'),
    ad: readToken('--text-disabled'),
    zone: {
      green: readToken('--zone-green'),
      yellow: readToken('--zone-yellow'),
      red: readToken('--zone-red'),
      none: readToken('--zone-none'),
    },
    edge: readToken('--border-strong'),
    edgeFaint: readToken('--border'),
    edgeStrong: readToken('--text-3'),
    ring: readToken('--accent'),
    outline: readToken('--bg'),
    text: readToken('--text'),
    labelBackground: readToken('--surface-raised'),
    font: readToken('--font-sans'),
  };
}

/** Fill of a node: by type, and for objects by zone. The shape (see LinkGraphCanvas) tells types apart without color. */
export function nodeFill(node: GraphNode, palette: GraphPalette): string {
  switch (node.type) {
    case 'object':
      return palette.zone[node.zone ?? 'none'];
    case 'developer':
      return palette.developer;
    case 'phone':
      return palette.phone;
    case 'account':
      return palette.account;
    case 'ad':
      return palette.ad;
  }
}
