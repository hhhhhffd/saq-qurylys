import type { Territory } from '@/api/types';

export interface LatLon {
  lat: number;
  lon: number;
}

/** Territory center as lat/lon, or null when the territory has none. */
export function toLatLon(territory: Pick<Territory, 'center_lat' | 'center_lon'>): LatLon | null {
  if (territory.center_lat == null || territory.center_lon == null) return null;
  return { lat: territory.center_lat, lon: territory.center_lon };
}

/** `GET /territories` returns a nested tree (`children`); a flat list is accepted too. */
export function flattenTerritories(items: Territory[]): Territory[] {
  const result: Territory[] = [];
  const visit = (node: Territory) => {
    result.push(node);
    node.children?.forEach(visit);
  };
  items.forEach(visit);
  return result;
}
