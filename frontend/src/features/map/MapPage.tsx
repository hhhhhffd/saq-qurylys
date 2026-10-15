import { useMemo, useState } from 'react';
import { Button } from '@mantine/core';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useDashboard } from '@/api/hooks/objects';
import { useDistricts } from '@/api/hooks/reference';
import type { Dashboard, Zone } from '@/api/types';
import { PageHeader } from '@/components/PageHeader';
import { QueryBoundary } from '@/components/QueryState';
import { ZoneDisclaimer } from '@/components/ZoneDisclaimer';
import { TerritoryFilter } from '@/features/objects/list/TerritoryFilter';
import { parseId, patchParams, useCityScope } from '@/features/objects/list/filters';
import { useFormat } from '@/i18n/useFormat';
import { toLatLon } from '@/lib/geo';
import { DashboardMap } from './DashboardMap';
import { ObjectList } from './ObjectList';
import { ZoneCounters } from './ZoneCounters';
import classes from './MapPage.module.css';

export function MapPage() {
  const { t } = useTranslation('map');
  const { t: common } = useTranslation();
  const format = useFormat();
  const [params, setParams] = useSearchParams();
  const territoryId = parseId(params.get('territory'));
  const districtId = parseId(params.get('district'));
  // Zone is a client-side narrowing of the loaded objects, so it stays out of the URL.
  const [zone, setZone] = useState<Zone | null>(null);

  const dashboard = useDashboard({ territory_id: territoryId ?? undefined, district_id: districtId ?? undefined });
  const updatedAt = dashboard.data?.last_updated_at ?? null;
  const hasFilters = territoryId !== null || districtId !== null || zone !== null;

  return (
    <>
      <PageHeader
        title={t('title')}
        subtitle={updatedAt ? common('lastUpdated', { value: format.dateTime(updatedAt) }) : undefined}
        actions={
          <>
            <Button component={Link} to="/signals" variant="default">
              {t('links.signals')}
            </Button>
            <Button component={Link} to="/ads" variant="default">
              {t('links.ads')}
            </Button>
          </>
        }
      />
      <div className={classes.filters}>
        <TerritoryFilter
          territoryId={territoryId}
          districtId={districtId}
          onChange={({ territory, district }) =>
            setParams((prev) =>
              patchParams(prev, {
                territory: territory === null ? null : String(territory),
                district: district === null ? null : String(district),
              }),
            )
          }
        />
        {hasFilters && (
          <Button
            variant="subtle"
            onClick={() => {
              setZone(null);
              setParams((prev) => patchParams(prev, { territory: null, district: null }));
            }}
          >
            {common('reset')}
          </Button>
        )}
      </div>
      <QueryBoundary query={dashboard}>
        {(data) => (
          <DashboardContent
            data={data}
            territoryId={territoryId}
            zone={zone}
            stale={dashboard.isPlaceholderData}
            onToggleZone={(next) => setZone((current) => (current === next ? null : next))}
          />
        )}
      </QueryBoundary>
    </>
  );
}

interface ContentProps {
  data: Dashboard;
  territoryId: number | null;
  zone: Zone | null;
  /** showing the previous filter's data while the new one loads */
  stale: boolean;
  onToggleZone: (zone: Zone) => void;
}

function DashboardContent({ data, territoryId, zone, stale, onToggleZone }: ContentProps) {
  const { t } = useTranslation('map');
  const navigate = useNavigate();
  const [highlightedId, setHighlightedId] = useState<number | null>(null);
  const { city } = useCityScope(territoryId);
  const { data: districts } = useDistricts(city?.id);

  // A stable array: the map pushes new data to MapLibre whenever this identity changes.
  const rows = useMemo(
    () => (zone === null ? data.objects : data.objects.filter((row) => row.zone === zone)),
    [data.objects, zone],
  );
  const withoutCoordinates = rows.filter((row) => row.lat === null || row.lon === null).length;

  return (
    <div className={classes.content} data-stale={stale || undefined}>
      <ZoneCounters counts={data.counts} active={zone} onToggle={onToggleZone} />
      <ZoneDisclaimer />
      <div className={classes.grid}>
        <div className={classes.mapColumn}>
          <DashboardMap
            objects={rows}
            districts={districts}
            fallbackCenter={city ? toLatLon(city) : null}
            highlightedId={highlightedId}
            onOpen={(id) => void navigate(`/objects/${id}`)}
          />
          {withoutCoordinates > 0 && (
            <p className={classes.note}>{t('map.withoutCoordinates', { count: withoutCoordinates })}</p>
          )}
        </div>
        <section className={`panel ${classes.listPanel}`} aria-label={t('list.title')}>
          <h2 className={classes.listTitle}>{t('list.title')}</h2>
          <div className={classes.scroll}>
            <ObjectList rows={rows} highlightedId={highlightedId} onHighlight={setHighlightedId} />
          </div>
        </section>
      </div>
    </div>
  );
}
