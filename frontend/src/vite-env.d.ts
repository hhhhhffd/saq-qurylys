/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** MapLibre style URL; defaults to OpenFreeMap "positron" */
  readonly VITE_MAP_STYLE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
