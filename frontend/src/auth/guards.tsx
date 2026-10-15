import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router';
import { useTranslation } from 'react-i18next';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { useAuth } from './useAuth';

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading, error, retry, logout } = useAuth();
  const location = useLocation();
  const { t } = useTranslation();

  if (loading) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <LoadingBlock />
      </div>
    );
  }
  if (error) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <div>
          <ErrorBlock error={error} onRetry={retry} />
          <div className="text-center">
            <Button variant="ghost" size="xs" onClick={logout}>
              {t('auth.logout')}
            </Button>
          </div>
        </div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  return <>{children}</>;
}

/** Sends users without the capability to their home screen. */
export function RequireCapability({
  capability,
  children,
}: {
  capability: 'canSeeRegistry' | 'canEditRegistry' | 'isAdmin';
  children: ReactNode;
}) {
  const auth = useAuth();
  if (!auth[capability]) return <Navigate to="/" replace />;
  return <>{children}</>;
}

/** Landing route: registry roles open the map, recipients open their signals. */
export function HomeRedirect() {
  const { canSeeRegistry } = useAuth();
  return <Navigate to={canSeeRegistry ? '/map' : '/signals'} replace />;
}
