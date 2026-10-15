import { useMemo, useState } from 'react';
import { Button, Tooltip } from '@mantine/core';
import { IconHistory, IconInfoCircle } from '@tabler/icons-react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useDashboard } from '@/api/hooks/objects';
import { useDistricts } from '@/api/hooks/reference';
import { useTimeline } from '@/api/hooks/timeline';
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
import { TimeMachineBar } from './TimeMachineBar';
import { countZones, rowsAtFrame, useTimeMachine } from './timeMachine';
import { ZoneCounters } from './ZoneCounters';
import classes from './MapPage.module.css';

/** Space at the bottom of the map that the time machine bar covers; markers are fitted above it. */
const TIME_BAR_INSET = 130;

export function MapPage() {
  const { t } = useTranslation('map');
  const { t: common } = useTranslation();
  const format = useFormat();
  const [params, setParams] = useSearchParams();
  const territoryId = parseId(params.get('territory'));
  const districtId = parseId(params.get('district'));
  // Zone is a client-side narrowing of the loaded objects, so it stays out of the URL.
  const [zone, setZone] = useState<Zone | null>(null);
  const [timeMachine, setTimeMachine] = useState(false);

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
            <Button
              variant={timeMachine ? 'filled' : 'default'}
              leftSection={<IconHistory size={16} stroke={1.8} />}
              aria-pressed={timeMachine}
              onClick={() => setTimeMachine((on) => !on)}
            >
              {t('timeMachine.toggle')}
            </Button>
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
            timeMachine={timeMachine}
            onCloseTimeMachine={() => setTimeMachine(false)}
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
  /** the time machine is open: the map can show the state of a past date */
  timeMachine: boolean;
  onCloseTimeMachine: () => void;
}

function DashboardContent({
  data,
  territoryId,
  zone,
  stale,
  onToggleZone,
  timeMachine,
  onCloseTimeMachine,
}: ContentProps) {
  const { t } = useTranslation('map');
  const navigate = useNavigate();
  const [highlightedId, setHighlightedId] = useState<number | null>(null);
  const { city } = useCityScope(territoryId);
  const { data: districts } = useDistricts(city?.id);

  const timeline = useTimeline(timeMachine);
  const frames = timeline.data?.frames;
  const machine = useTimeMachine(frames?.length ?? 0, timeMachine);
  // Today (the last frame), a closed time machine and a history that is still loading all show live data.
  const frame = timeMachine && !machine.isToday ? frames?.[machine.index] : undefined;
  const snapshot = useMemo(() => (frame ? rowsAtFrame(data.objects, frame) : data.objects), [data.objects, frame]);
  const counts = useMemo(() => (frame ? countZones(snapshot) : data.counts), [data.counts, frame, snapshot]);
  // A stable array: the map pushes new data to MapLibre whenever this identity changes.
  const rows = useMemo(
    () => (zone === null ? snapshot : snapshot.filter((row) => row.zone === zone)),
    [snapshot, zone],
  );
  const withoutCoordinates = rows.filter((row) => row.lat === null || row.lon === null).length;

  return (
    <div className={classes.content} data-stale={stale || undefined}>
      <ZoneCounters counts={counts} active={zone} onToggle={onToggleZone} />
      <ZoneDisclaimer />
      <div className={classes.grid}>
        <div className={classes.mapColumn}>
          <DashboardMap
            objects={rows}
            districts={districts}
            fallbackCenter={city ? toLatLon(city) : null}
            highlightedId={highlightedId}
            onOpen={(id) => void navigate(`/objects/${id}`)}
            historical={frame !== undefined}
            bottomInset={timeMachine ? TIME_BAR_INSET : 0}
          >
            {timeMachine && <TimeMachineBar timeline={timeline} machine={machine} onClose={onCloseTimeMachine} />}
          </DashboardMap>
          {timeMachine && (
            <p className={classes.note}>
              <Tooltip
                label={t('timeMachine.noteHint')}
                multiline
                w={300}
                events={{ hover: true, focus: true, touch: true }}
              >
                <span className={classes.hint} tabIndex={0}>
                  <IconInfoCircle size={14} stroke={1.8} aria-hidden />
                  {t('timeMachine.note')}
                </span>
              </Tooltip>
            </p>
          )}
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
