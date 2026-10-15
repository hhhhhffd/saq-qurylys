import { useContext, useMemo } from 'react';
import { AuthContext, permissionsFor } from './context';

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside <AuthProvider>');
  const role = context.user?.role;
  const permissions = useMemo(() => permissionsFor(role), [role]);
  return { ...context, ...permissions };
}
