import { IconMovie, IconPhoto, IconRefresh } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useRetryAsset } from '@/api/hooks/vision';
import type { VisionAsset } from '@/api/types';
import { Chip } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { Button } from '@/components/ui/button';
import { useEnum } from '@/i18n/useEnum';
import { ASSET_STATUS_TONE, formatSize, formatTimestamp } from './constants';

export function AssetsPanel({ assets }: { assets: VisionAsset[] }) {
  const { t } = useTranslation('vision');
  const { t: tc } = useTranslation();
  const e = useEnum();
  const retry = useRetryAsset();
  const nameOf = (asset: VisionAsset) => asset.original_name ?? t('assets.unnamed', { id: asset.id });

  return (
    <Panel title={t('assets.title')} flush>
      {assets.length === 0 ? (
        <p className="m-0 px-4 py-4 text-text-3">{t('assets.empty')}</p>
      ) : (
        <ul>
          {assets.map((asset) => {
            const inWork = asset.status === 'queued' || asset.status === 'processing';
            return (
              <li key={asset.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border px-3 py-2 text-sm first:border-t-0">
                <span className="text-text-3" aria-hidden>
                  {asset.kind === 'video' ? <IconMovie size={16} /> : <IconPhoto size={16} />}
                </span>
                <span className="min-w-0 flex-1 [overflow-wrap:anywhere]">
                  {nameOf(asset)}{' '}
                  <span className="text-text-3 tabular-nums">
                    {formatSize(asset.size_bytes)}
                    {asset.duration_ms !== null && ` · ${formatTimestamp(asset.duration_ms)}`}
                    {asset.status === 'ready' && ` · ${t('assets.frames', { count: asset.frames_count })}`}
                  </span>
                </span>
                {inWork && (
                  <span
                    className="h-1.5 w-28 overflow-hidden rounded-full bg-surface-sunken"
                    role="progressbar"
                    aria-label={nameOf(asset)}
                    aria-valuemin={0}
                    aria-valuemax={100}
                    aria-valuenow={asset.progress}
                  >
                    <span className="block h-full rounded-full bg-primary" style={{ width: `${asset.progress}%` }} />
                  </span>
                )}
                <Chip tone={ASSET_STATUS_TONE[asset.status]}>{e('vision_asset_status', asset.status)}</Chip>
                {asset.status === 'failed' && asset.kind === 'video' && (
                  <Button
                    size="xs"
                    variant="secondary"
                    loading={retry.isPending && retry.variables === asset.id}
                    onClick={() => retry.mutate(asset.id)}
                  >
                    <IconRefresh />
                    {tc('retry')}
                  </Button>
                )}
                {asset.status === 'failed' && asset.error_code && (
                  <span className="basis-full text-xs text-zone-red-ink">
                    {tc(`errors.${asset.error_code}`, { defaultValue: asset.error_code })}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
