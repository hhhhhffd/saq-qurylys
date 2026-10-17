import { useRef, useState, type DragEvent } from 'react';
import { IconUpload } from '@tabler/icons-react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { apiUpload, ApiError, toFormData } from '@/api/client';
import { qk } from '@/api/keys';
import { errorMessage } from '@/api/queryClient';
import type { VisionAsset, VisionConfig } from '@/api/types';
import { Chip } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { ACCEPT, fileKind, formatSize } from './constants';

type UploadState = 'waiting' | 'uploading' | 'done' | 'duplicate' | 'error';

interface UploadItem {
  key: number;
  name: string;
  size: number;
  state: UploadState;
  progress: number;
  error?: string;
}

interface Props {
  sessionId: number;
  config: VisionConfig;
  /** assets the session already has: a returned asset that is among them was a duplicate upload */
  assets: VisionAsset[];
}

let nextKey = 0;

/** Drop zone and the per-file list. Files go one request each, one after another, with real upload progress. */
export function UploadPanel({ sessionId, config, assets }: Props) {
  const { t } = useTranslation('vision');
  const qc = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<UploadItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);

  const patch = (key: number, change: Partial<UploadItem>) =>
    setItems((prev) => prev.map((item) => (item.key === key ? { ...item, ...change } : item)));

  const upload = async (files: File[]) => {
    if (files.length === 0) return;
    const queued: { key: number; file: File }[] = [];
    const added: UploadItem[] = files.map((file) => {
      const key = nextKey++;
      const kind = fileKind(file);
      const limitMb = kind === 'video' ? config.max_video_mb : config.max_photo_mb;
      const base = { key, name: file.name, size: file.size, progress: 0 };
      if (kind === null) return { ...base, state: 'error', error: t('upload.unsupported') };
      if (file.size === 0) return { ...base, state: 'error', error: t('upload.empty') };
      if (file.size > limitMb * 1024 * 1024) return { ...base, state: 'error', error: t('upload.tooLarge', { mb: limitMb }) };
      queued.push({ key, file });
      return { ...base, state: 'waiting' };
    });
    setItems((prev) => [...added, ...prev]);

    setBusy(true);
    const known = new Set(assets.map((asset) => asset.id));
    for (const { key, file } of queued) {
      patch(key, { state: 'uploading' });
      try {
        const asset = await apiUpload<VisionAsset>(
          `/vision/sessions/${sessionId}/assets`,
          toFormData({ file }),
          (progress) => patch(key, { progress }),
        );
        patch(key, { state: known.has(asset.id) ? 'duplicate' : 'done', progress: 100 });
        known.add(asset.id);
        void qc.invalidateQueries({ queryKey: qk.vision });
      } catch (error) {
        patch(key, { state: 'error', error: error instanceof ApiError ? errorMessage(error) : String(error) });
      }
    }
    setBusy(false);
  };

  const onDrop = (event: DragEvent) => {
    event.preventDefault();
    setDragging(false);
    if (!busy) void upload([...event.dataTransfer.files]);
  };

  return (
    <Panel title={t('upload.title')}>
      <div
        className={cn(
          'flex flex-col items-center gap-2 rounded border border-dashed border-border-strong px-4 py-5 text-center text-sm text-text-2',
          dragging && 'border-primary bg-hover',
        )}
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          className="sr-only"
          tabIndex={-1}
          data-testid="vision-file-input"
          aria-label={t('upload.inputLabel')}
          onChange={(event) => {
            const files = [...(event.target.files ?? [])];
            event.target.value = '';
            void upload(files);
          }}
        />
        <Button type="button" variant="secondary" disabled={busy} loading={busy} onClick={() => inputRef.current?.click()}>
          <IconUpload />
          {t('upload.choose')}
        </Button>
        <p className="m-0">{t('upload.hint')}</p>
        <p className="m-0 text-xs text-text-3">
          {t('upload.limits', { photo: config.max_photo_mb, video: config.max_video_mb, minutes: Math.round(config.max_duration_seconds / 60) })}
        </p>
      </div>
      {items.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1.5" aria-label={t('upload.listLabel')}>
          {items.map((item) => (
            <li key={item.key} className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              <span className="min-w-0 flex-1 truncate [overflow-wrap:anywhere]" title={item.name}>
                {item.name} <span className="text-text-3 tabular-nums">{formatSize(item.size)}</span>
              </span>
              {item.state === 'uploading' && (
                <span
                  className="h-1.5 w-32 overflow-hidden rounded-full bg-surface-sunken"
                  role="progressbar"
                  aria-label={item.name}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={item.progress}
                >
                  <span className="block h-full rounded-full bg-primary" style={{ width: `${item.progress}%` }} />
                </span>
              )}
              <Chip tone={item.state === 'done' ? 'green' : item.state === 'error' ? 'red' : item.state === 'duplicate' ? 'yellow' : 'neutral'}>
                {t(`upload.state.${item.state}`, { percent: item.progress })}
              </Chip>
              {item.error && <span className="basis-full text-xs text-zone-red-ink">{item.error}</span>}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
