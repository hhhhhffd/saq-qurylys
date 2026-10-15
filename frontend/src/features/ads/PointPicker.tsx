import { lazy, Suspense, useState, type ReactNode } from 'react';
import { Group, Loader, NumberInput, Stack, Text } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import classes from './PointPicker.module.css';

// maplibre-gl is heavy: the map chunk loads only when an outdoor ad is being added.
const PointMap = lazy(() => import('./PointMap'));

function supportsWebgl(): boolean {
  const canvas = document.createElement('canvas');
  return canvas.getContext('webgl2') !== null || canvas.getContext('webgl') !== null;
}

interface Props {
  lat: number | string;
  lon: number | string;
  onChange: (lat: number | string, lon: number | string) => void;
  error?: ReactNode;
}

/** Map click sets the point; the coordinate fields stay usable without WebGL. */
export function PointPicker({ lat, lon, onChange, error }: Props) {
  const { t } = useTranslation('ads');
  const [webgl] = useState(supportsWebgl);
  const [mapFailed, setMapFailed] = useState(false);
  const mapAvailable = webgl && !mapFailed;

  return (
    <Stack gap="xs">
      <div>
        <Text size="sm" fw={500}>
          {t('point.title')}
        </Text>
        <Text size="xs" c="dimmed">
          {mapAvailable ? t('point.hint') : t('point.mapUnavailable')}
        </Text>
      </div>
      {mapAvailable && (
        <Suspense
          fallback={
            <div className={classes.placeholder}>
              <Loader size="sm" />
            </div>
          }
        >
          <PointMap lat={lat} lon={lon} onPick={onChange} onUnavailable={() => setMapFailed(true)} />
        </Suspense>
      )}
      <Group grow align="flex-start">
        <NumberInput
          label={t('point.lat')}
          value={lat}
          onChange={(value) => onChange(value, lon)}
          min={-90}
          max={90}
          decimalScale={6}
          hideControls
          error={error ? true : undefined}
        />
        <NumberInput
          label={t('point.lon')}
          value={lon}
          onChange={(value) => onChange(lat, value)}
          min={-180}
          max={180}
          decimalScale={6}
          hideControls
          error={error ? true : undefined}
        />
      </Group>
      {error && (
        <p className={classes.error} role="alert">
          {error}
        </p>
      )}
    </Stack>
  );
}
