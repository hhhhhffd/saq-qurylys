import { useEffect, useRef } from 'react';
import { MapLibreMap, Marker, NavigationControl } from '@/lib/maplibre';
import { useTranslation } from 'react-i18next';
import { useTerritoryList } from '@/lib/territories';
import { useAuth } from '@/auth/useAuth';
import { toLatLon } from '@/lib/geo';
import classes from './PointPicker.module.css';

const STYLE_URL = import.meta.env.VITE_MAP_STYLE_URL || 'https://tiles.openfreemap.org/styles/positron';
/** Geographic center of Kazakhstan, shown when the user's territory has no center. */
const COUNTRY_CENTER: [number, number] = [67.0, 48.0];
const COUNTRY_ZOOM = 4;
const TERRITORY_ZOOM = 10;
const POINT_ZOOM = 14;

interface Props {
  lat: number | string;
  lon: number | string;
  onPick: (lat: number, lon: number) => void;
  /** the map could not be created (e.g. no WebGL) */
  onUnavailable: () => void;
}

export default function PointMap({ lat, lon, onPick, onUnavailable }: Props) {
  const { t } = useTranslation('ads');
  const { user } = useAuth();
  const { territories } = useTerritoryList();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markerRef = useRef<Marker | null>(null);
  const callbacksRef = useRef({ onPick, onUnavailable });
  const ownTerritory = territories.find((territory) => territory.id === user?.territory_id);
  // The map is created once; these describe its first view only.
  const initialViewRef = useRef({
    center: ownTerritory ? toLatLon(ownTerritory) : null,
    point: typeof lat === 'number' && typeof lon === 'number' ? { lat, lon } : null,
  });

  useEffect(() => {
    callbacksRef.current = { onPick, onUnavailable };
  });

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const { center, point } = initialViewRef.current;
    const start = point ?? center;

    let map: MapLibreMap;
    try {
      map = new MapLibreMap({
        container,
        style: STYLE_URL,
        center: start ? [start.lon, start.lat] : COUNTRY_CENTER,
        zoom: point ? POINT_ZOOM : center ? TERRITORY_ZOOM : COUNTRY_ZOOM,
        attributionControl: { compact: true },
      });
    } catch {
      callbacksRef.current.onUnavailable();
      return;
    }
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right');
    map.on('click', (event) => callbacksRef.current.onPick(event.lngLat.lat, event.lngLat.lng));
    mapRef.current = map;

    return () => {
      markerRef.current?.remove();
      markerRef.current = null;
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (typeof lat !== 'number' || typeof lon !== 'number') {
      markerRef.current?.remove();
      markerRef.current = null;
      return;
    }
    if (markerRef.current) {
      markerRef.current.setLngLat([lon, lat]);
    } else {
      const element = document.createElement('div');
      element.className = classes.marker;
      markerRef.current = new Marker({ element }).setLngLat([lon, lat]).addTo(map);
    }
    // Coordinates typed into the fields may be off-screen.
    if (!map.getBounds().contains([lon, lat])) map.easeTo({ center: [lon, lat] });
  }, [lat, lon]);

  return <div ref={containerRef} className={classes.map} role="region" aria-label={t('point.mapLabel')} />;
}
