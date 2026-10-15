import { useTranslation } from 'react-i18next';
import { Combobox } from '@/components/ui/combobox';
import { parseId, useCityScope } from './filters';

interface Props {
  territoryId: number | null;
  districtId: number | null;
  /** a changed city always resets the district */
  onChange: (next: { territory: number | null; district: number | null }) => void;
}

/** City select (only when the user sees several cities) and district select of the chosen city. */
export function TerritoryFilter({ territoryId, districtId, onChange }: Props) {
  const { t } = useTranslation('objects');
  const { cities, city, districts } = useCityScope(territoryId);

  return (
    <>
      {cities.length > 1 && (
        <Combobox
          aria-label={t('list.filters.city')}
          placeholder={t('list.filters.allCities')}
          options={cities.map((item) => ({ value: String(item.id), label: item.name }))}
          value={territoryId === null ? null : String(territoryId)}
          onChange={(value) => onChange({ territory: parseId(value), district: null })}
          clearable
          className="w-full sm:w-48"
        />
      )}
      {cities.length > 0 && (
        <Combobox
          aria-label={t('list.filters.district')}
          placeholder={t('list.filters.allDistricts')}
          options={districts.map((item) => ({ value: String(item.id), label: item.name }))}
          value={districtId === null ? null : String(districtId)}
          onChange={(value) => onChange({ territory: territoryId, district: parseId(value) })}
          disabled={city === null}
          clearable
          className="w-full sm:w-48"
        />
      )}
    </>
  );
}
