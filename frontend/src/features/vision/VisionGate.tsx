import type { ReactNode } from 'react';
import { Navigate } from 'react-router';
import { useVisionConfig } from '@/api/hooks/vision';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';

/** The vision routes exist only while the backend module is on (`GET /vision/config` is 404 otherwise). */
export function VisionGate({ children }: { children: ReactNode }) {
  const config = useVisionConfig();
  if (config.isPending) return <LoadingBlock />;
  if (config.isError) return <ErrorBlock error={config.error} onRetry={() => void config.refetch()} />;
  if (!config.data?.enabled) return <Navigate to="/" replace />;
  return <>{children}</>;
}
