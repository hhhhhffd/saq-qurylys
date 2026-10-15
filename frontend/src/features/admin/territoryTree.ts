import type { Territory } from '@/api/types';

export interface TerritoryRow {
  territory: Territory;
  depth: number;
}

/** Depth-first rows of the nested territory tree: every parent is followed by its children. */
export function territoryRows(tree: Territory[]): TerritoryRow[] {
  const rows: TerritoryRow[] = [];
  const visit = (territory: Territory, depth: number) => {
    rows.push({ territory, depth });
    territory.children.forEach((child) => visit(child, depth + 1));
  };
  tree.forEach((territory) => visit(territory, 0));
  return rows;
}

/** `Region › City` labels by territory id, so equal city names stay distinguishable. */
export function territoryLabels(territories: Territory[]): Map<number, string> {
  const byId = new Map(territories.map((territory) => [territory.id, territory]));
  const labelOf = (territory: Territory): string => {
    const parent = territory.parent_id === null ? undefined : byId.get(territory.parent_id);
    return parent ? `${labelOf(parent)} › ${territory.name}` : territory.name;
  };
  return new Map(territories.map((territory) => [territory.id, labelOf(territory)]));
}

/** Time zones of Kazakhstan (IANA). */
export const KZ_TIME_ZONES = [
  'Asia/Almaty',
  'Asia/Qostanay',
  'Asia/Aqtobe',
  'Asia/Aqtau',
  'Asia/Atyrau',
  'Asia/Oral',
  'Asia/Qyzylorda',
] as const;
