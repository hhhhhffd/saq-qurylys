import { lazy, Suspense, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { NumberInput } from '@/components/form/NumberInput';
import { Spinner } from '@/components/ui/spinner';

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
    <div className="flex flex-col gap-2">
      <div>
        <p className="m-0 text-xs font-medium text-text-2">{t('point.title')}</p>
        <p className="m-0 text-xs text-text-3">{mapAvailable ? t('point.hint') : t('point.mapUnavailable')}</p>
      </div>
      {mapAvailable && (
        <Suspense
          fallback={
            <div className="grid h-60 place-items-center rounded border border-border-strong bg-surface-sunken">
              <Spinner />
            </div>
          }
        >
          <PointMap lat={lat} lon={lon} onPick={onChange} onUnavailable={() => setMapFailed(true)} />
        </Suspense>
      )}
      <div className="grid grid-cols-2 items-start gap-3">
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
      </div>
      {error && (
        <p className="m-0 text-xs text-zone-red-ink" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
