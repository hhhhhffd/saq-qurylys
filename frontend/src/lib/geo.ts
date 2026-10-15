import type { Territory } from '@/api/types';

export interface LatLon {
  lat: number;
  lon: number;
}

/** Territory centers may be GeoJSON points or `{lat, lon}`. */
export function toLatLon(point: Territory['center']): LatLon | null {
  if (!point) return null;
  if ('coordinates' in point) return { lon: point.coordinates[0], lat: point.coordinates[1] };
  return { lat: point.lat, lon: point.lon };
}

/** `GET /territories` may return a nested tree or a flat list; always return a flat list. */
export function flattenTerritories(items: Territory[]): Territory[] {
  const result: Territory[] = [];
  const visit = (node: Territory) => {
    result.push(node);
    node.children?.forEach(visit);
  };
  items.forEach(visit);
  return result;
}
