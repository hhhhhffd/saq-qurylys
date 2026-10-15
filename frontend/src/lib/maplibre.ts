import { setWorkerUrl } from 'maplibre-gl';
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import 'maplibre-gl/dist/maplibre-gl.css';

// maplibre-gl 6 does not locate its worker on its own under Vite; without this the vector
// style fails to load. Import maplibre-gl from this module so the worker is always configured.
setWorkerUrl(workerUrl);

export * from 'maplibre-gl';
