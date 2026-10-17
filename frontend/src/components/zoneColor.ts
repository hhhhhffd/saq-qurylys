import type { Zone } from '@/api/types';

export function zoneTone(zone: Zone | null | undefined): 'green' | 'yellow' | 'red' | 'none' {
  return zone ?? 'none';
}

/** Solid zone color (CSS variable) for markers, dots and bars. */
export function zoneColor(zone: Zone | null | undefined): string {
  return `var(--zone-${zoneTone(zone)})`;
}

/** Concrete hex values for canvas/WebGL (maplibre) where CSS variables are unavailable. Mirror tokens.css. */
export const ZONE_HEX = {
  green: '#1f9d57',
  yellow: '#d99a0b',
  red: '#d92d20',
  none: '#8a85a3',
} as const;
