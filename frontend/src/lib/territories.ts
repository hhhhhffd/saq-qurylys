import { useMemo } from 'react';
import { useDistricts, useTerritories } from '@/api/hooks/reference';
import type { Territory } from '@/api/types';
import { flattenTerritories } from './geo';

/** Flat list of every territory the user can see. */
export function useTerritoryList(): { territories: Territory[]; isPending: boolean } {
  const { data, isPending } = useTerritories();
  const territories = useMemo(() => (data ? flattenTerritories(data) : []), [data]);
  return { territories, isPending };
}

/** Cities (level `city`) visible to the user: objects belong to a city. */
export function useCities(): { cities: Territory[]; isPending: boolean } {
  const { territories, isPending } = useTerritoryList();
  const cities = useMemo(() => territories.filter((t) => t.level === 'city'), [territories]);
  return { cities, isPending };
}

export interface DistrictOption {
  id: number;
  name: string;
}

/** Districts of a city, read from the GeoJSON feature collection (`properties.id` or feature `id`). */
export function useDistrictOptions(territoryId: number | null | undefined): { districts: DistrictOption[]; isPending: boolean } {
  const { data, isPending } = useDistricts(territoryId);
  const districts = useMemo(
    () =>
      (data?.features ?? [])
        .map((feature) => ({ id: Number(feature.properties.id ?? feature.id), name: feature.properties.name }))
        .filter((district) => Number.isFinite(district.id)),
    [data],
  );
  return { districts, isPending: territoryId != null && isPending };
}
