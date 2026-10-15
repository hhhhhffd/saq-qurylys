import { fileURLToPath } from 'node:url';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  // Pre-bundle everything up front: screens are lazy-loaded, so otherwise Vite discovers
  // dependencies mid-session and re-optimizes ("Outdated Optimize Dep" reloads).
  optimizeDeps: {
    include: [
      '@mantine/core',
      '@mantine/dates',
      '@mantine/form',
      '@mantine/hooks',
      '@mantine/modals',
      '@mantine/notifications',
      '@tabler/icons-react',
      '@tanstack/react-query',
      '@tanstack/react-table',
      'dayjs',
      'dayjs/locale/kk',
      'dayjs/locale/ru',
      'i18next',
      'maplibre-gl',
      'react',
      'react-dom/client',
      'react-i18next',
      'react-router',
    ],
  },
  server: {
    port: 5173,
    proxy: {
      // API_PROXY_TARGET lets the dev server point at another backend (default: local FastAPI).
      '/api': { target: process.env.API_PROXY_TARGET ?? 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 1500,
  },
});
