import { request, type APIRequestContext } from '@playwright/test';
import { BASE_URL } from './env';
import { CREDENTIALS, type Role } from './users';

/** The backend through the same origin as the UI (nginx or the Vite proxy), signed in as a role. */
export interface Api {
  get<T>(path: string): Promise<T>;
  post<T>(path: string, data?: unknown): Promise<T>;
  patch<T>(path: string, data: unknown): Promise<T>;
  dispose(): Promise<void>;
}

async function parse<T>(response: Awaited<ReturnType<APIRequestContext['get']>>, what: string): Promise<T> {
  if (!response.ok()) throw new Error(`${what} failed: ${response.status()} ${await response.text()}`);
  return (await response.json()) as T;
}

export async function apiAs(role: Role): Promise<Api> {
  const { username, password } = CREDENTIALS[role];
  if (!password) throw new Error(`No password for ${role}: set SAQ_ADMIN_PASSWORD (e2e/run.sh does it)`);
  const context = await request.newContext({ baseURL: BASE_URL });
  const login = await parse<{ access_token: string }>(
    await context.post('/api/v1/auth/login', { data: { username, password } }),
    `login ${username}`,
  );
  const headers = { Authorization: `Bearer ${login.access_token}` };
  const url = (path: string) => `/api/v1${path}`;
  return {
    get: async (path) => parse(await context.get(url(path), { headers }), `GET ${path}`),
    post: async (path, data) => parse(await context.post(url(path), { headers, data }), `POST ${path}`),
    patch: async (path, data) => parse(await context.patch(url(path), { headers, data }), `PATCH ${path}`),
    dispose: () => context.dispose(),
  };
}

// ---------------------------------------------------------------- demo data

interface Page<T> {
  items: T[];
}

export interface ObjectSummary {
  id: number;
  name: string;
  score: number | null;
  zone: string | null;
}

export async function findObject(api: Api, name: string): Promise<ObjectSummary> {
  const found = await api.get<Page<ObjectSummary>>(`/objects?q=${encodeURIComponent(name)}&limit=50`);
  const object = found.items.find((item) => item.name === name);
  if (!object) throw new Error(`Demo object not found: ${name}`);
  return object;
}

export async function objectScore(api: Api, objectId: number): Promise<number | null> {
  return (await api.get<ObjectSummary>(`/objects/${objectId}`)).score;
}

interface Signal {
  id: number;
  status: 'requires_confirmation' | 'returned' | 'sent' | 'responded' | 'closed';
}

/**
 * Takes every unfinished signal card of an object to `closed` (return → send → answer → close), so that a run that
 * stopped half way does not block the next one: an object can have only one open card.
 */
export async function closeSignalCards(objectId: number): Promise<void> {
  const mio = await apiAs('mio');
  const gask = await apiAs('gask');
  try {
    const cards = await mio.get<Page<Signal>>(`/signals?object_id=${objectId}&limit=100`);
    for (const { id, status } of cards.items) {
      if (status === 'closed') continue;
      if (status === 'returned') await mio.patch(`/signals/${id}`, { recipient: 'gask' });
      if (status === 'returned' || status === 'requires_confirmation') {
        await mio.post(`/signals/${id}/confirm-and-send`, { recipient: 'gask' });
      }
      if (status !== 'responded') await gask.post(`/signals/${id}/response`, { response_text: 'E2E: cleanup' });
      await mio.post(`/signals/${id}/close`);
    }
  } finally {
    await mio.dispose();
    await gask.dispose();
  }
}
