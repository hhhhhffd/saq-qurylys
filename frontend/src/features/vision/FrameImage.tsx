import { IconFileOff } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useFrameImage } from '@/api/hooks/vision';
import { Spinner } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';

interface Props {
  frameId: number;
  variant: 'preview' | 'original';
  alt: string;
  className?: string;
  imgClassName?: string;
  onLoad?: (size: { width: number; height: number }) => void;
}

/** A frame fetched with the Bearer token; shows a spinner or an error mark in the same box. */
export function FrameImage({ frameId, variant, alt, className, imgClassName, onLoad }: Props) {
  const { t } = useTranslation();
  const { data, isPending, isError } = useFrameImage(frameId, variant);
  if (isPending || isError) {
    return (
      <span className={cn('flex items-center justify-center bg-surface-sunken text-text-3', className)} title={isError ? t('states.loadError') : undefined}>
        {isError ? <IconFileOff size={18} stroke={1.5} /> : <Spinner role="presentation" aria-hidden className="size-3.5" />}
      </span>
    );
  }
  return (
    <img
      src={data.url}
      alt={alt}
      className={cn('block', className, imgClassName)}
      draggable={false}
      onLoad={(event) => onLoad?.({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })}
    />
  );
}
