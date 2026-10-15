import { fileURLToPath } from 'node:url';

/** The app under test: `docker compose` frontend (8080) by default, `pnpm dev` is http://localhost:5173. */
export const BASE_URL = process.env.E2E_BASE_URL ?? 'http://localhost:8080';

/** Password of the demo_* accounts (README, «Тестовый сценарий»). */
export const DEMO_PASSWORD = process.env.SAQ_DEMO_PASSWORD ?? 'demo-saq-2026';

/** Password of `admin` (INITIAL_ADMIN_PASSWORD in .env); `e2e/run.sh` exports it. Admin specs skip without it. */
export const ADMIN_PASSWORD = process.env.SAQ_ADMIN_PASSWORD;

export const AUTH_DIR = fileURLToPath(new URL('../.auth/', import.meta.url));
