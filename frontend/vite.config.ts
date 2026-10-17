import { fileURLToPath } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  // Pre-bundle everything up front: screens are lazy-loaded, so otherwise Vite discovers
  // dependencies mid-session and re-optimizes ("Outdated Optimize Dep" reloads).
  optimizeDeps: {
    include: [
      '@hookform/resolvers/zod',
      '@tabler/icons-react',
      '@tanstack/react-query',
      '@tanstack/react-table',
      'class-variance-authority',
      'clsx',
      'date-fns',
      'date-fns/locale/kk',
      'date-fns/locale/ru',
      'dayjs',
      'dayjs/locale/kk',
      'dayjs/locale/ru',
      'i18next',
      'maplibre-gl',
      'motion/react',
      'radix-ui',
      'react',
      'react-day-picker',
      'react-dom/client',
      'react-hook-form',
      'react-i18next',
      'react-markdown',
      'react-router',
      'sonner',
      'tailwind-merge',
      'zod',
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
