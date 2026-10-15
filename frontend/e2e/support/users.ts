import { ADMIN_PASSWORD, AUTH_DIR, DEMO_PASSWORD } from './env';

export type Role = 'mio' | 'gask' | 'police' | 'admin';

export const CREDENTIALS: Record<Role, { username: string; password: string | undefined }> = {
  mio: { username: 'demo_mio', password: DEMO_PASSWORD },
  gask: { username: 'demo_gask', password: DEMO_PASSWORD },
  police: { username: 'demo_police', password: DEMO_PASSWORD },
  admin: { username: 'admin', password: ADMIN_PASSWORD },
};

/** Where `auth.setup.ts` keeps the session (localStorage with the token) of a role. */
export function authFile(role: Role): string {
  return `${AUTH_DIR}${role}.json`;
}
