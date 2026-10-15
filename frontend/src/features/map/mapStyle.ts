import type { StyleSpecification } from '@/lib/maplibre';

export const MAP_STYLE_URL = import.meta.env.VITE_MAP_STYLE_URL || 'https://tiles.openfreemap.org/styles/positron';

/** Used when the style above cannot be loaded (offline, blocked host): plain OpenStreetMap raster tiles. */
export const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      maxzoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors',
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
};

/** Overview of Kazakhstan, used while there is nothing to fit to. */
export const KAZAKHSTAN_VIEW = { center: [66.9, 48.0] as [number, number], zoom: 3.4 };

export const CITY_ZOOM = 10.5;

/** MapLibre cannot read CSS variables, so design tokens are resolved to concrete colors. */
export function readToken(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function prefersReducedMotion(): boolean {
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

let webGlAvailable: boolean | undefined;

/** MapLibre throws while constructing the map when no WebGL2 context can be created. */
export function isWebGlAvailable(): boolean {
  if (webGlAvailable === undefined) {
    const context = document.createElement('canvas').getContext('webgl2');
    webGlAvailable = context !== null;
    context?.getExtension('WEBGL_lose_context')?.loseContext();
  }
  return webGlAvailable;
}
