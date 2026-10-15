import type { Zone } from '@/api/types';
import { useCities, useDistrictOptions } from '@/lib/territories';

export const ZONES: readonly Zone[] = ['green', 'yellow', 'red'];

export function isZone(value: string | null): value is Zone {
  return value === 'green' || value === 'yellow' || value === 'red';
}

/** Positive integer from a URL parameter, otherwise null. */
export function parseId(value: string | null): number | null {
  if (value === null) return null;
  const id = Number(value);
  return Number.isInteger(id) && id > 0 ? id : null;
}

/** Copy of the URL parameters with `patch` applied; a `null` value removes the key. */
export function patchParams(prev: URLSearchParams, patch: Record<string, string | null>): URLSearchParams {
  const next = new URLSearchParams(prev);
  for (const [key, value] of Object.entries(patch)) {
    if (value === null) next.delete(key);
    else next.set(key, value);
  }
  return next;
}

/**
 * The city whose districts can be chosen: the one from the URL, or the only city
 * the user can see (then no city select is shown).
 */
export function useCityScope(territoryId: number | null) {
  const { cities } = useCities();
  const city = cities.find((item) => item.id === (territoryId ?? (cities.length === 1 ? cities[0].id : null))) ?? null;
  const { districts } = useDistrictOptions(city?.id);
  return { cities, city, districts };
}
