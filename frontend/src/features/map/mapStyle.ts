import type { Map as MapLibreMap, StyleSpecification } from '@/lib/maplibre';

export const MAP_STYLE_URL = import.meta.env.VITE_MAP_STYLE_URL || 'https://tiles.openfreemap.org/styles/positron';

/** MapLibre's controls and attribution in the light theme; its CSS is unlayered, so the overrides need `!`. */
export const MAP_CONTROLS_CLASS = [
  '[&_.maplibregl-ctrl-group]:rounded! [&_.maplibregl-ctrl-group]:border! [&_.maplibregl-ctrl-group]:border-border-strong! [&_.maplibregl-ctrl-group]:bg-surface-raised! [&_.maplibregl-ctrl-group]:shadow-none!',
  '[&_.maplibregl-ctrl-group_button]:border-border! [&_.maplibregl-ctrl-group_button:hover]:bg-hover!',
  '[&_.maplibregl-ctrl-attrib]:bg-surface-glass! [&_.maplibregl-ctrl-attrib]:text-text-3! [&_.maplibregl-ctrl-attrib_a]:text-text-2!',
].join(' ');

/** Used when the style above cannot be loaded (offline, blocked host): plain OpenStreetMap raster tiles. */
export const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  // Glyphs for the score digits on the markers.
  glyphs: 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
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

/** Colors of the light basemap that have no token: lilac-tinted water, parks and roads that stay visible on the page color. */
const WATER = '#dde2f4';
const PARK = '#e7eee8';
const LAND_LIGHT = '#efedf7';
const BUILDING = '#e6e2f1';
const ROAD_MINOR = '#d3cee6';
const ROAD_MAJOR = '#bdb5dc';

/**
 * Recolors the loaded style to the app palette. Layers are matched by type and id prefix, so other styles
 * (VITE_MAP_STYLE_URL) get a reasonable result too; layers with no rule keep their own colors.
 */
export function recolorBasemap(map: MapLibreMap): void {
  const background = readToken('--bg');
  const border = readToken('--border-strong');
  const label = readToken('--text-3');
  const set = (id: string, property: Parameters<MapLibreMap['setPaintProperty']>[1], value: string) => map.setPaintProperty(id, property, value);

  for (const layer of map.getStyle().layers) {
    const { id } = layer;
    switch (layer.type) {
      case 'raster':
        // Fallback OSM tiles: soften the colors so they sit calmly next to the UI.
        map.setPaintProperty(id, 'raster-saturation', -0.5);
        break;
      case 'background':
        set(id, 'background-color', background);
        break;
      case 'fill':
        if (id.startsWith('water')) set(id, 'fill-color', WATER);
        else if (id.startsWith('building')) {
          set(id, 'fill-color', BUILDING);
          set(id, 'fill-outline-color', border);
        } else if (id.startsWith('landcover_wood') || id.startsWith('landuse_park')) set(id, 'fill-color', PARK);
        else if (id.startsWith('landuse_residential')) set(id, 'fill-color', LAND_LIGHT);
        else set(id, 'fill-color', background);
        break;
      case 'line':
        if (id.startsWith('boundary')) set(id, 'line-color', border);
        else if (id.startsWith('waterway')) set(id, 'line-color', WATER);
        else if (id.includes('casing')) set(id, 'line-color', background);
        else if (id.startsWith('railway')) set(id, 'line-color', id.endsWith('dashline') ? background : ROAD_MINOR);
        else if (id.startsWith('highway_major') || id.startsWith('highway_motorway')) set(id, 'line-color', ROAD_MAJOR);
        else set(id, 'line-color', ROAD_MINOR);
        break;
      case 'symbol':
        if (layer.layout?.['text-field'] === undefined) break;
        set(id, 'text-color', label);
        set(id, 'text-halo-color', background);
        break;
    }
  }
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
