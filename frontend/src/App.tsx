import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router';
import { HomeRedirect, RequireAuth, RequireCapability } from '@/auth/guards';
import { AppLayout } from '@/layout/AppLayout';
import { LoginPage } from '@/features/login/LoginPage';
import { useTranslation } from 'react-i18next';
import { EmptyState } from '@/components/QueryState';
import { VisionGate } from '@/features/vision/VisionGate';

// Screens are code-split; the map brings in maplibre-gl, which is the heaviest dependency.
const MapPage = lazy(() => import('@/features/map/MapPage').then((m) => ({ default: m.MapPage })));
const ObjectsPage = lazy(() => import('@/features/objects/ObjectsPage').then((m) => ({ default: m.ObjectsPage })));
const ObjectDetailPage = lazy(() =>
  import('@/features/objects/ObjectDetailPage').then((m) => ({ default: m.ObjectDetailPage })),
);
const AdsPage = lazy(() => import('@/features/ads/AdsPage').then((m) => ({ default: m.AdsPage })));
const SourcesPage = lazy(() => import('@/features/sources/SourcesPage').then((m) => ({ default: m.SourcesPage })));
const WorkPage = lazy(() => import('@/features/work/WorkPage').then((m) => ({ default: m.WorkPage })));
const GraphPage = lazy(() => import('@/features/graph/GraphPage').then((m) => ({ default: m.GraphPage })));
const SignalsPage = lazy(() => import('@/features/signals/SignalsPage').then((m) => ({ default: m.SignalsPage })));
const SignalDetailPage = lazy(() =>
  import('@/features/signals/SignalDetailPage').then((m) => ({ default: m.SignalDetailPage })),
);
const VisionPage = lazy(() => import('@/features/vision/VisionPage').then((m) => ({ default: m.VisionPage })));
const SessionPage = lazy(() => import('@/features/vision/SessionPage').then((m) => ({ default: m.SessionPage })));
const ControlPage = lazy(() =>
  import('@/features/assignments/ControlPage').then((m) => ({ default: m.ControlPage })),
);
const AdminPage = lazy(() => import('@/features/admin/AdminPage').then((m) => ({ default: m.AdminPage })));

// Dev-only visual reference of the theme; the dynamic import is dropped from production builds.
const KitPage = import.meta.env.DEV ? lazy(() => import('@/features/kit/KitPage').then((m) => ({ default: m.KitPage }))) : null;

function NotFound() {
  const { t } = useTranslation();
  return <EmptyState>{t('states.notFound')}</EmptyState>;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      {KitPage && (
        <Route
          path="/_kit"
          element={
            <Suspense fallback={null}>
              <KitPage />
            </Suspense>
          }
        />
      )}
      <Route
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<HomeRedirect />} />
        <Route
          path="work"
          element={
            <RequireCapability capability="canSeeRegistry">
              <WorkPage />
            </RequireCapability>
          }
        />
        <Route
          path="control"
          element={
            <RequireCapability capability="canEditRegistry">
              <ControlPage />
            </RequireCapability>
          }
        />
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
        <Route
          path="sources"
          element={
            <RequireCapability capability="canEditRegistry">
              <SourcesPage />
            </RequireCapability>
          }
        />
        <Route
          path="vision"
          element={
            <RequireCapability capability="canEditRegistry">
              <VisionGate>
                <VisionPage />
              </VisionGate>
            </RequireCapability>
          }
        />
        <Route
          path="vision/:id"
          element={
            <RequireCapability capability="canEditRegistry">
              <VisionGate>
                <SessionPage />
              </VisionGate>
            </RequireCapability>
          }
        />
        <Route
          path="graph"
          element={
            <RequireCapability capability="canSeeRegistry">
              <GraphPage />
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
