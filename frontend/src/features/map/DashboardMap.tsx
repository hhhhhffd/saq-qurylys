import { useEffect, useMemo, useRef, useState } from 'react';
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
import {
  CITY_ZOOM,
  FALLBACK_STYLE,
  KAZAKHSTAN_VIEW,
  MAP_STYLE_URL,
  isWebGlAvailable,
  prefersReducedMotion,
  readToken,
} from './mapStyle';
import classes from './DashboardMap.module.css';

const OBJECTS_SOURCE = 'objects';
const DISTRICTS_SOURCE = 'districts';
const DISTRICTS_LAYER = 'districts-line';
const HIGHLIGHT_LAYER = 'objects-highlight';
const CIRCLE_LAYER = 'objects-circle';
/** Transparent and larger than the visible dot, so small markers are easy to hit with a finger. */
const HIT_LAYER = 'objects-hit';
const NO_OBJECT = -1;
const FIT_ANIMATION_MS = 600;

// Overlapping markers: the riskier zone is drawn on top.
const ZONE_RANK = { none: 0, green: 1, yellow: 2, red: 3 } as const;

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
  ZONE_HEX.none,
];

const EMPTY_COLLECTION = { type: 'FeatureCollection' as const, features: [] };

function toObjectCollection(objects: ObjectRow[]) {
  const features = objects.flatMap((row) =>
    row.lat === null || row.lon === null
      ? []
      : [
          {
            type: 'Feature' as const,
            geometry: { type: 'Point' as const, coordinates: [row.lon, row.lat] },
            properties: {
              id: row.id,
              code: row.code,
              name: row.name,
              score: row.score,
              zone: row.zone ?? 'none',
              is_demo: row.is_demo,
              rank: ZONE_RANK[row.zone ?? 'none'],
              lon: row.lon,
              lat: row.lat,
            },
          },
        ],
  );
  return { type: 'FeatureCollection' as const, features };
}

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
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 3.5, 8, 5.5, 12, 8, 16, 11],
      'circle-color': zoneColorExpression,
      'circle-stroke-color': readToken('--surface-raised'),
      'circle-stroke-width': 1.5,
    },
  });
  map.addLayer({
    id: HIT_LAYER,
    type: 'circle',
    source: OBJECTS_SOURCE,
    layout: { 'circle-sort-key': ['get', 'rank'] },
    paint: { 'circle-radius': 14, 'circle-opacity': 0 },
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
}

export function DashboardMap(props: Props) {
  const { t } = useTranslation('map');
  if (!isWebGlAvailable()) {
    return (
      <div className={classes.frame}>
        <p className={classes.unavailable} role="status">
          {t('map.unavailable')}
        </p>
      </div>
    );
  }
  return <MapCanvas {...props} />;
}

function MapCanvas({ objects, districts, fallbackCenter, highlightedId, onOpen }: Props) {
  const { t } = useTranslation('map');
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const hoveredIdRef = useRef<number | null>(null);
  const hasFittedRef = useRef(false);
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
      className: classes.popup,
    });

    map.on('style.load', () => {
      styleLoaded = true;
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
      content.className = classes.popupBody;
      const code = document.createElement('span');
      code.className = classes.popupCode;
      code.textContent = String(properties.code);
      const name = document.createElement('strong');
      name.textContent = String(properties.name);
      const score = document.createElement('span');
      score.className = classes.popupScore;
      score.textContent =
        typeof properties.score === 'number'
          ? t('map.popupScore', { score: properties.score })
          : t('zone.none', { ns: 'enums' });
      content.append(code, name, score);
      if (properties.is_demo) {
        const demo = document.createElement('span');
        demo.className = classes.popupCode;
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

  const objectCollection = useMemo(() => toObjectCollection(objects), [objects]);
  useEffect(() => {
    const source = mapRef.current?.getSource(OBJECTS_SOURCE);
    if (source instanceof GeoJSONSource) void source.setData(objectCollection);
  }, [objectCollection, styleVersion]);

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
        { padding: 48, maxZoom: 15, duration },
      );
    } else if (centerLat !== null && centerLon !== null) {
      map.easeTo({ center: [centerLon, centerLat], zoom: CITY_ZOOM, duration });
    } else {
      map.easeTo({ center: KAZAKHSTAN_VIEW.center, zoom: KAZAKHSTAN_VIEW.zoom, duration });
    }
  }, [west, south, east, north, centerLat, centerLon, styleVersion]);

  return (
    <div className={classes.frame} role="region" aria-label={t('map.label')}>
      <div ref={containerRef} className={classes.canvas} />
    </div>
  );
}
