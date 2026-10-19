import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  GeoJSONSource,
  Map as MapLibreMap,
  NavigationControl,
  Popup,
  type AddLayerObject,
} from '@/lib/maplibre';
import { useTranslation } from 'react-i18next';
import type { DistrictCollection, ObjectRow } from '@/api/types';
import { ZONE_HEX } from '@/components/zoneColor';
import type { LatLon } from '@/lib/geo';
import { markerColor, markerFeatures, paintMarkers, type Rgba } from './markers';
import {
  CITY_ZOOM,
  FALLBACK_STYLE,
  KAZAKHSTAN_VIEW,
  MAP_CONTROLS_CLASS,
  MAP_STYLE_URL,
  isWebGlAvailable,
  prefersReducedMotion,
  readToken,
  recolorBasemap,
} from './mapStyle';

// Frame and popup, restyled for the light theme. MapLibre's own CSS is light and unlayered, so it beats Tailwind's
// layered utilities: the overrides of its classes need `!` (the controls are in MAP_CONTROLS_CLASS).
const FRAME_CLASS = `relative h-[var(--map-h,320px)] overflow-hidden rounded-lg bg-surface-sunken shadow-1 ${MAP_CONTROLS_CLASS}`;
const POPUP_CLASS = [
  'pointer-events-none',
  '[&_.maplibregl-popup-content]:rounded! [&_.maplibregl-popup-content]:border! [&_.maplibregl-popup-content]:border-border-strong! [&_.maplibregl-popup-content]:bg-surface-raised! [&_.maplibregl-popup-content]:px-3! [&_.maplibregl-popup-content]:py-2! [&_.maplibregl-popup-content]:font-sans! [&_.maplibregl-popup-content]:text-sm! [&_.maplibregl-popup-content]:text-text! [&_.maplibregl-popup-content]:shadow-2!',
  '[&_.maplibregl-popup-tip]:hidden!',
].join(' ');
const POPUP_BODY_CLASS = 'flex flex-col gap-px';
const POPUP_META_CLASS = 'text-xs text-text-2 tabular-nums';

const OBJECTS_SOURCE = 'objects';
const DISTRICTS_SOURCE = 'districts';
const DISTRICTS_LAYER = 'districts-line';
const HIGHLIGHT_LAYER = 'objects-highlight';
const CIRCLE_LAYER = 'objects-circle';
/** Transparent and larger than the visible dot, so small markers are easy to hit with a finger. */
const SCORE_LAYER = 'objects-score';
const HIT_LAYER = 'objects-hit';
const NO_OBJECT = -1;
const FIT_ANIMATION_MS = 600;
const FIT_PADDING = 48;

type CirclePaint = NonNullable<Extract<AddLayerObject, { type: 'circle' }>['paint']>;

const zoneColorExpression: CirclePaint['circle-color'] = [
  'match',
  ['get', 'zone'],
  'green',
  ZONE_HEX.green,
  'yellow',
  ZONE_HEX.yellow,
  'red',
  ZONE_HEX.red,
  'ghost',
  markerColor('ghost'),
  ZONE_HEX.none,
];

const EMPTY_COLLECTION = { type: 'FeatureCollection' as const, features: [] };

function objectsBounds(objects: ObjectRow[]): [number, number, number, number] | null {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const row of objects) {
    if (row.lat === null || row.lon === null) continue;
    west = Math.min(west, row.lon);
    east = Math.max(east, row.lon);
    south = Math.min(south, row.lat);
    north = Math.max(north, row.lat);
  }
  return west === Infinity ? null : [west, south, east, north];
}

/** Sources and layers live in the style, so they are added again whenever the style is replaced. */
function addObjectLayers(map: MapLibreMap) {
  if (map.getSource(OBJECTS_SOURCE)) return;
  map.addSource(DISTRICTS_SOURCE, { type: 'geojson', data: EMPTY_COLLECTION });
  map.addSource(OBJECTS_SOURCE, { type: 'geojson', data: EMPTY_COLLECTION });

  map.addLayer({
    id: DISTRICTS_LAYER,
    type: 'line',
    source: DISTRICTS_SOURCE,
    paint: {
      'line-color': readToken('--text-3'),
      'line-width': 1.2,
      'line-opacity': 0.6,
      'line-dasharray': [4, 3],
    },
  });
  map.addLayer({
    id: HIGHLIGHT_LAYER,
    type: 'circle',
    source: OBJECTS_SOURCE,
    filter: ['==', ['get', 'id'], NO_OBJECT],
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 9, 8, 11, 12, 14, 16, 18],
      'circle-color': zoneColorExpression,
      'circle-opacity': 0.22,
      'circle-stroke-color': zoneColorExpression,
      'circle-stroke-width': 2,
    },
  });
  map.addLayer({
    id: CIRCLE_LAYER,
    type: 'circle',
    source: OBJECTS_SOURCE,
    layout: { 'circle-sort-key': ['get', 'rank'] },
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 4, 6, 9, 8, 13, 16, 15],
      // The colors are set per marker (paintMarkers), so a change of zone can fade.
      'circle-color': ['get', 'color'],
      'circle-stroke-color': '#ffffff',
      'circle-stroke-width': 1.5,
    },
  });
  // The risk score inside the marker. Yellow is too light for white digits, so it gets dark ink.
  map.addLayer({
    id: SCORE_LAYER,
    type: 'symbol',
    source: OBJECTS_SOURCE,
    minzoom: 6,
    layout: {
      'text-field': ['case', ['==', ['typeof', ['get', 'score']], 'number'], ['to-string', ['round', ['get', 'score']]], '—'],
      'text-font': ['Noto Sans Bold'],
      'text-size': ['interpolate', ['linear'], ['zoom'], 6, 9, 8, 12, 16, 13],
      'text-allow-overlap': true,
      'text-ignore-placement': true,
      'symbol-sort-key': ['get', 'rank'],
    },
    paint: {
      'text-color': ['match', ['get', 'zone'], 'yellow', readToken('--text'), '#ffffff'],
    },
  });
  map.addLayer({
    id: HIT_LAYER,
    type: 'circle',
    source: OBJECTS_SOURCE,
    layout: { 'circle-sort-key': ['get', 'rank'] },
    paint: { 'circle-radius': 16, 'circle-opacity': 0 },
  });
}

function setHighlight(map: MapLibreMap, id: number | null) {
  if (map.getLayer(HIGHLIGHT_LAYER)) map.setFilter(HIGHLIGHT_LAYER, ['==', ['get', 'id'], id ?? NO_OBJECT]);
}

interface Props {
  /** objects to show; those without coordinates are skipped */
  objects: ObjectRow[];
  /** district boundaries of the selected city */
  districts: DistrictCollection | undefined;
  /** where to look when there are no objects */
  fallbackCenter: LatLon | null;
  /** object highlighted from outside (hovered list row) */
  highlightedId: number | null;
  onOpen: (id: number) => void;
  /** the objects are shown as they were at a past moment: those without a score then are faint ghosts */
  historical?: boolean;
  /** space at the bottom of the map taken by `children`, kept clear of markers when the map fits them */
  bottomInset?: number;
  /** drawn over the map */
  children?: ReactNode;
}

export function DashboardMap(props: Props) {
  const { t } = useTranslation('map');
  if (!isWebGlAvailable()) {
    return (
      <div className={FRAME_CLASS}>
        <p className="m-0 flex h-full items-center justify-center p-6 text-center text-text-2" role="status">
          {t('map.unavailable')}
        </p>
        {props.children}
      </div>
    );
  }
  return <MapCanvas {...props} />;
}

function MapCanvas({
  objects,
  districts,
  fallbackCenter,
  highlightedId,
  onOpen,
  historical = false,
  bottomInset = 0,
  children,
}: Props) {
  const { t } = useTranslation('map');
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const hoveredIdRef = useRef<number | null>(null);
  const hasFittedRef = useRef(false);
  /** colors the markers have on screen, for the fade between two states of the map */
  const drawnColorsRef = useRef(new Map<number, Rgba>());
  const latestRef = useRef({ onOpen, highlightedId });
  /** Incremented each time a style (re)loads: sources and layers must then be filled again. */
  const [styleVersion, setStyleVersion] = useState(0);

  useEffect(() => {
    latestRef.current = { onOpen, highlightedId };
  });

  // The map is created once per mount (and per language, for the control labels); data changes go through setData.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let styleLoaded = false;
    let usedFallbackStyle = false;
    const map = new MapLibreMap({
      container,
      style: MAP_STYLE_URL,
      center: KAZAKHSTAN_VIEW.center,
      zoom: KAZAKHSTAN_VIEW.zoom,
      attributionControl: { compact: true },
      locale: {
        'NavigationControl.ZoomIn': t('map.zoomIn'),
        'NavigationControl.ZoomOut': t('map.zoomOut'),
        'AttributionControl.ToggleAttribution': t('map.toggleAttribution'),
        'AttributionControl.MapFeedback': t('map.mapFeedback'),
      },
    });
    mapRef.current = map;
    hasFittedRef.current = false;
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right');

    const popup = new Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 12,
      maxWidth: '280px',
      className: POPUP_CLASS,
    });

    map.on('style.load', () => {
      styleLoaded = true;
      recolorBasemap(map);
      addObjectLayers(map);
      setStyleVersion((version) => version + 1);
    });
    // The style request failed (offline, blocked host): switch to plain OSM tiles once.
    map.on('error', () => {
      if (styleLoaded || usedFallbackStyle) return;
      usedFallbackStyle = true;
      map.setStyle(FALLBACK_STYLE, { diff: false });
    });

    map.on('mousemove', HIT_LAYER, (event) => {
      const properties = event.features?.[0]?.properties;
      if (!properties) return;
      map.getCanvas().style.cursor = 'pointer';
      const id = Number(properties.id);
      if (hoveredIdRef.current === id) return;
      hoveredIdRef.current = id;
      setHighlight(map, id);

      const content = document.createElement('div');
      content.className = POPUP_BODY_CLASS;
      const code = document.createElement('span');
      code.className = POPUP_META_CLASS;
      code.textContent = String(properties.code);
      const name = document.createElement('strong');
      name.textContent = String(properties.name);
      const score = document.createElement('span');
      score.className = POPUP_META_CLASS;
      score.textContent =
        typeof properties.score === 'number'
          ? t('map.popupScore', { score: properties.score })
          : t('zone.none', { ns: 'enums' });
      content.append(code, name, score);
      if (properties.is_demo) {
        const demo = document.createElement('span');
        demo.className = POPUP_META_CLASS;
        demo.textContent = t('demo.badge', { ns: 'common' });
        content.append(demo);
      }
      popup.setLngLat([Number(properties.lon), Number(properties.lat)]).setDOMContent(content).addTo(map);
    });
    map.on('mouseleave', HIT_LAYER, () => {
      map.getCanvas().style.cursor = '';
      hoveredIdRef.current = null;
      setHighlight(map, latestRef.current.highlightedId);
      popup.remove();
    });
    map.on('click', HIT_LAYER, (event) => {
      const id = Number(event.features?.[0]?.properties.id);
      if (Number.isFinite(id)) latestRef.current.onOpen(id);
    });

    return () => {
      popup.remove();
      map.remove();
      mapRef.current = null;
      hoveredIdRef.current = null;
    };
  }, [t]);

  useEffect(() => {
    const source = mapRef.current?.getSource(OBJECTS_SOURCE);
    if (!(source instanceof GeoJSONSource)) return;
    return paintMarkers(source, markerFeatures(objects, historical), drawnColorsRef.current, historical && !prefersReducedMotion());
  }, [objects, historical, styleVersion]);

  const districtCollection = useMemo(
    () => ({
      type: 'FeatureCollection' as const,
      features: districts?.features.filter((feature) => feature.geometry !== null) ?? [],
    }),
    [districts],
  );
  useEffect(() => {
    const source = mapRef.current?.getSource(DISTRICTS_SOURCE);
    if (source instanceof GeoJSONSource) void source.setData(districtCollection);
  }, [districtCollection, styleVersion]);

  useEffect(() => {
    const map = mapRef.current;
    if (map) setHighlight(map, hoveredIdRef.current ?? highlightedId);
  }, [highlightedId, styleVersion]);

  const bounds = useMemo(() => objectsBounds(objects), [objects]);
  const [west, south, east, north] = bounds ?? [null, null, null, null];
  const centerLat = fallbackCenter?.lat ?? null;
  const centerLon = fallbackCenter?.lon ?? null;
  // Refits only when the extent changes, so periodic refetches do not reset the user's pan and zoom.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || styleVersion === 0) return;
    const duration = hasFittedRef.current && !prefersReducedMotion() ? FIT_ANIMATION_MS : 0;
    hasFittedRef.current = true;
    if (west !== null && south !== null && east !== null && north !== null) {
      map.fitBounds(
        [
          [west, south],
          [east, north],
        ],
        { padding: { top: FIT_PADDING, left: FIT_PADDING, right: FIT_PADDING, bottom: FIT_PADDING + bottomInset }, maxZoom: 15, duration },
      );
    } else if (centerLat !== null && centerLon !== null) {
      map.easeTo({ center: [centerLon, centerLat], zoom: CITY_ZOOM, duration });
    } else {
      map.easeTo({ center: KAZAKHSTAN_VIEW.center, zoom: KAZAKHSTAN_VIEW.zoom, duration });
    }
  }, [west, south, east, north, centerLat, centerLon, bottomInset, styleVersion]);

  return (
    <div className={FRAME_CLASS} role="region" aria-label={t('map.label')}>
      <div ref={containerRef} className="absolute! inset-0" />
      {children}
    </div>
  );
}
