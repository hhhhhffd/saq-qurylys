import { createContext } from 'react';
import type { Role, User } from '@/api/types';

export interface AuthState {
  user: User | null;
  /** true while a stored token is being validated via /auth/me */
  loading: boolean;
  /** /auth/me failed for a reason other than 401 (e.g. API unreachable) */
  error: Error | null;
  retry: () => void;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthState | null>(null);

/** Role capabilities from SPEC §4. */
export function permissionsFor(role: Role | undefined) {
  return {
    isAdmin: role === 'admin',
    /** CRUD of registry data, ads and phrase confirmation */
    canEditRegistry: role === 'admin' || role === 'mio_officer',
    /** create/edit/confirm/return signal cards */
    canManageSignals: role === 'mio_officer',
    /** recipients enter the result of a signal card directed to them */
    isRecipient: role === 'gask' || role === 'law_enforcement',
    /** dashboard, objects and ads are visible */
    canSeeRegistry: role === 'admin' || role === 'mio_officer',
  };
}
