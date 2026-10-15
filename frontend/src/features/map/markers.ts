import type { ObjectRow } from '@/api/types';
import { ZONE_HEX } from '@/components/zoneColor';
import type { GeoJSONSource } from '@/lib/maplibre';

/** What a marker is drawn as: its zone, or a ghost (no score yet at the moment the map shows). */
export type MarkerZone = 'green' | 'yellow' | 'red' | 'none' | 'ghost';

export type Rgba = readonly [red: number, green: number, blue: number, alpha: number];

const GHOST_ALPHA = 0.3;
/** MapLibre cannot animate data-driven colors, so the fade is drawn by hand; past this many markers it is skipped. */
const MAX_FADED_MARKERS = 1500;
const COLOR_FADE_MS = 350;

function fromHex(hex: string, alpha = 1): Rgba {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255, alpha];
}

const COLORS: Record<MarkerZone, Rgba> = {
  green: fromHex(ZONE_HEX.green),
  yellow: fromHex(ZONE_HEX.yellow),
  red: fromHex(ZONE_HEX.red),
  none: fromHex(ZONE_HEX.none),
  ghost: fromHex(ZONE_HEX.none, GHOST_ALPHA),
};

// Overlapping markers: the riskier zone is drawn on top.
const ZONE_RANK: Record<MarkerZone, number> = { ghost: 0, none: 0, green: 1, yellow: 2, red: 3 };

function css([red, green, blue, alpha]: Rgba): string {
  return `rgba(${Math.round(red)}, ${Math.round(green)}, ${Math.round(blue)}, ${alpha.toFixed(3)})`;
}

export function markerColor(zone: MarkerZone): string {
  return css(COLORS[zone]);
}

function sameColor(a: Rgba, b: Rgba): boolean {
  return a.every((channel, index) => channel === b[index]);
}

function mixColors(from: Rgba, to: Rgba, progress: number): Rgba {
  if (progress >= 1) return to;
  const mix = (index: 0 | 1 | 2 | 3) => from[index] + (to[index] - from[index]) * progress;
  return [mix(0), mix(1), mix(2), mix(3)];
}

export interface MarkerProperties {
  id: number;
  code: string;
  name: string;
  score: number | null;
  zone: MarkerZone;
  is_demo: boolean;
  rank: number;
  lon: number;
  lat: number;
}

export interface MarkerFeature {
  type: 'Feature';
  geometry: { type: 'Point'; coordinates: [number, number] };
  properties: MarkerProperties;
}

/** Objects without coordinates are skipped. With `historical`, an object without a zone is a ghost. */
export function markerFeatures(objects: ObjectRow[], historical: boolean): MarkerFeature[] {
  return objects.flatMap((row) => {
    if (row.lat === null || row.lon === null) return [];
    const zone: MarkerZone = row.zone ?? (historical ? 'ghost' : 'none');
    return [
      {
        type: 'Feature' as const,
        geometry: { type: 'Point' as const, coordinates: [row.lon, row.lat] as [number, number] },
        properties: {
          id: row.id,
          code: row.code,
          name: row.name,
          score: row.score,
          zone,
          is_demo: row.is_demo,
          rank: ZONE_RANK[zone],
          lon: row.lon,
          lat: row.lat,
        },
      },
    ];
  });
}

/**
 * Puts the markers on the map. With `fade`, a marker whose zone changed since the last drawing blends from the
 * color it had on screen to the new one. `drawn` remembers the colors on screen between calls, so a fade that is
 * interrupted by the next frame carries on from where it was. Returns a function that stops a running fade.
 */
export function paintMarkers(
  source: GeoJSONSource,
  features: MarkerFeature[],
  drawn: Map<number, Rgba>,
  fade: boolean,
): () => void {
  const targets = features.map((feature) => COLORS[feature.properties.zone]);
  const starts = features.map((feature, index) => drawn.get(feature.properties.id) ?? targets[index]);

  const draw = (progress: number) => {
    drawn.clear();
    const painted = features.map((feature, index) => {
      const color = mixColors(starts[index], targets[index], progress);
      drawn.set(feature.properties.id, color);
      return { ...feature, properties: { ...feature.properties, color: css(color) } };
    });
    void source.setData({ type: 'FeatureCollection', features: painted });
  };

  const fading =
    fade && features.length <= MAX_FADED_MARKERS && starts.some((start, index) => !sameColor(start, targets[index]));
  if (!fading) {
    draw(1);
    return () => undefined;
  }

  draw(0);
  const startedAt = performance.now();
  let frame = 0;
  const tick = (now: number) => {
    const progress = Math.min(1, (now - startedAt) / COLOR_FADE_MS);
    draw(1 - (1 - progress) ** 3);
    if (progress < 1) frame = requestAnimationFrame(tick);
  };
  frame = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(frame);
}
