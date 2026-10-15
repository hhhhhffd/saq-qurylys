import { lazy } from 'react';
import { Navigate, Route, Routes } from 'react-router';
import { HomeRedirect, RequireAuth, RequireCapability } from '@/auth/guards';
import { AppLayout } from '@/layout/AppLayout';
import { LoginPage } from '@/features/login/LoginPage';
import { useTranslation } from 'react-i18next';
import { EmptyState } from '@/components/QueryState';

// Screens are code-split; the map brings in maplibre-gl, which is the heaviest dependency.
const MapPage = lazy(() => import('@/features/map/MapPage').then((m) => ({ default: m.MapPage })));
const ObjectsPage = lazy(() => import('@/features/objects/ObjectsPage').then((m) => ({ default: m.ObjectsPage })));
const ObjectDetailPage = lazy(() =>
  import('@/features/objects/ObjectDetailPage').then((m) => ({ default: m.ObjectDetailPage })),
);
const AdsPage = lazy(() => import('@/features/ads/AdsPage').then((m) => ({ default: m.AdsPage })));
const SignalsPage = lazy(() => import('@/features/signals/SignalsPage').then((m) => ({ default: m.SignalsPage })));
const SignalDetailPage = lazy(() =>
  import('@/features/signals/SignalDetailPage').then((m) => ({ default: m.SignalDetailPage })),
);
const AdminPage = lazy(() => import('@/features/admin/AdminPage').then((m) => ({ default: m.AdminPage })));

function NotFound() {
  const { t } = useTranslation();
  return <EmptyState>{t('states.notFound')}</EmptyState>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<HomeRedirect />} />
        <Route
          path="map"
          element={
            <RequireCapability capability="canSeeRegistry">
              <MapPage />
            </RequireCapability>
          }
        />
        <Route
          path="objects"
          element={
            <RequireCapability capability="canSeeRegistry">
              <ObjectsPage />
            </RequireCapability>
          }
        />
        <Route
          path="objects/:id"
          element={
            <RequireCapability capability="canSeeRegistry">
              <ObjectDetailPage />
            </RequireCapability>
          }
        />
        <Route
          path="ads"
          element={
            <RequireCapability capability="canSeeRegistry">
              <AdsPage />
            </RequireCapability>
          }
        />
        <Route path="signals" element={<SignalsPage />} />
        <Route path="signals/:id" element={<SignalDetailPage />} />
        <Route
          path="admin/:section?"
          element={
            <RequireCapability capability="isAdmin">
              <AdminPage />
            </RequireCapability>
          }
        />
        <Route path="*" element={<NotFound />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
