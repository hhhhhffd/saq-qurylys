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
  green: '#3f8f5b',
  yellow: '#d49a1f',
  red: '#c2453d',
  none: '#9a9a95',
} as const;
