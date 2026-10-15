import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useCaptureAd } from '@/api/hooks/ads';
import type { Platform } from '@/api/types';
import { SelectInput } from '@/components/form/SelectInput';
import { TextInput } from '@/components/form/TextInput';
import { ObjectSelect } from '@/components/ObjectSelect';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useEnumOptions } from '@/i18n/useEnum';
import { CAPTURE_PLATFORMS, parsePlatform } from './constants';
import { isHttpUrl } from './url';

interface Props {
  open: boolean;
  onClose: () => void;
  /** called with the id of the new publication (its capture is still pending) */
  onCreated: (adId: number) => void;
}

export function CaptureModal({ open, onClose, onCreated }: Props) {
  const { t } = useTranslation('ads');
  const { t: tc } = useTranslation('common');
  const options = useEnumOptions();
  const captureAd = useCaptureAd();

  const schema = useMemo(
    () =>
      z.object({
        url: z
          .string()
          .trim()
          .min(1, tc('required'))
          .refine(isHttpUrl, t('capture.urlInvalid')),
        object_id: z.number().nullable(),
        platform: z.custom<Platform>().nullable(),
      }),
    [t, tc],
  );
  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { url: '', object_id: null as number | null, platform: null as Platform | null },
  });

  const close = () => {
    reset();
    onClose();
  };

  const submit = handleSubmit((values) =>
    captureAd.mutate(
      { url: values.url, object_id: values.object_id, platform: values.platform ?? undefined },
      {
        onSuccess: (ad) => {
          reset();
          onCreated(ad.id);
          onClose();
        },
      },
    ),
  );

  return (
    <Dialog open={open} onOpenChange={(next) => !next && close()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('capture.title')}</DialogTitle>
        </DialogHeader>
        <DialogDescription>{t('capture.hint')}</DialogDescription>
        <form onSubmit={submit} noValidate className="flex flex-col gap-3">
          <TextInput
            label={t('capture.url')}
            placeholder="https://"
            inputMode="url"
            required
            autoFocus
            error={errors.url?.message}
            {...register('url')}
          />
          <Controller
            control={control}
            name="object_id"
            render={({ field }) => (
              <ObjectSelect
                label={t('capture.object')}
                placeholder={t('capture.objectPlaceholder')}
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
          <Controller
            control={control}
            name="platform"
            render={({ field }) => (
              <SelectInput
                label={t('capture.platform')}
                description={t('capture.platformHint')}
                data={options('platform', CAPTURE_PLATFORMS)}
                value={field.value}
                onChange={(value) => field.onChange(parsePlatform(value))}
                clearable
              />
            )}
          />
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={close}>
              {tc('cancel')}
            </Button>
            <Button type="submit" loading={captureAd.isPending}>
              {t('capture.submit')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
