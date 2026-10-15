import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, getToken, setToken, setUnauthorizedHandler } from '@/api/client';
import { qk } from '@/api/keys';
import type { LoginResponse, User } from '@/api/types';
import { getStoredLanguage, setLanguage } from '@/i18n';
import { AuthContext, type AuthState } from './context';

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [token, setTokenState] = useState<string | null>(getToken);

  const me = useQuery({
    queryKey: qk.me,
    queryFn: () => api<User>('/auth/me'),
    enabled: token !== null,
    retry: false,
    staleTime: Infinity,
  });

  const logout = useCallback(() => {
    setToken(null);
    setTokenState(null);
    qc.clear();
  }, [qc]);

  // Any 401 from the API (expired or revoked token) sends the user back to the login screen.
  useEffect(() => {
    setUnauthorizedHandler(logout);
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  const login = useCallback(
    async (username: string, password: string) => {
      const response = await api<LoginResponse>('/auth/login', { method: 'POST', body: { username, password } });
      setToken(response.access_token);
      setTokenState(response.access_token);
      qc.setQueryData(qk.me, response.user);
      if (!getStoredLanguage()) setLanguage(response.user.locale);
    },
    [qc],
  );

  const value = useMemo<AuthState>(
    () => ({
      user: token ? (me.data ?? null) : null,
      loading: token !== null && me.isPending,
      error: token !== null && me.isError ? me.error : null,
      retry: () => void me.refetch(),
      login,
      logout,
    }),
    [token, me, login, logout],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}
