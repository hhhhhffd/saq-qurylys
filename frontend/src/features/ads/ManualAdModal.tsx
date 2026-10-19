import { useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { IconPhoto, IconX } from '@tabler/icons-react';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useCreateManualAd } from '@/api/hooks/ads';
import type { Platform } from '@/api/types';
import { DateTimeInput } from '@/components/form/DateTimeInput';
import { FileInput } from '@/components/form/FileInput';
import { SelectInput } from '@/components/form/SelectInput';
import { SwitchInput } from '@/components/form/SwitchInput';
import { TextArea } from '@/components/form/TextArea';
import { TextInput } from '@/components/form/TextInput';
import { ObjectSelect } from '@/components/ObjectSelect';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useEnumOptions } from '@/i18n/useEnum';
import { PLATFORMS, parsePlatform } from './constants';
import { PointPicker } from './PointPicker';
import { isHttpUrl } from './url';

interface Photo {
  file: File;
  /** object URL for the preview; revoked when the photo is removed or the form is closed */
  previewUrl: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (adId: number) => void;
}

const emptyValues = {
  text: '',
  platform: 'other' as Platform,
  url: '',
  object_id: null as number | null,
  /** `YYYY-MM-DD HH:mm:ss` from the picker, local time */
  published_at: null as string | null,
  is_outdoor: false,
  lat: '' as number | string,
  lon: '' as number | string,
};

export function ManualAdModal({ open, onClose, onCreated }: Props) {
  const { t } = useTranslation('ads');
  const { t: tc } = useTranslation('common');
  const options = useEnumOptions();
  const createAd = useCreateManualAd();
  const [photos, setPhotos] = useState<Photo[]>([]);

  const schema = useMemo(
    () =>
      z
        .object({
          text: z.string().trim().min(1, tc('required')),
          platform: z.custom<Platform>(),
          url: z
            .string()
            .trim()
            .refine((value) => value === '' || isHttpUrl(value), t('capture.urlInvalid')),
          object_id: z.number().nullable(),
          published_at: z.string().nullable(),
          is_outdoor: z.boolean(),
          lat: z.union([z.number(), z.string()]),
          lon: z.union([z.number(), z.string()]),
        })
        .superRefine((values, context) => {
          if (!values.is_outdoor) return;
          for (const key of ['lat', 'lon'] as const) {
            if (typeof values[key] !== 'number') context.addIssue({ code: 'custom', path: [key], message: t('point.required') });
          }
        }),
    [t, tc],
  );
  const {
    register,
    control,
    handleSubmit,
    reset,
    setValue,
    getValues,
    formState: { errors },
  } = useForm({ resolver: zodResolver(schema), defaultValues: emptyValues });
  const isOutdoor = useWatch({ control, name: 'is_outdoor' });
  const lat = useWatch({ control, name: 'lat' });
  const lon = useWatch({ control, name: 'lon' });

  const resetAll = () => {
    photos.forEach((photo) => URL.revokeObjectURL(photo.previewUrl));
    setPhotos([]);
    reset(emptyValues);
  };

  const close = () => {
    resetAll();
    onClose();
  };

  const setOutdoor = (outdoor: boolean) => {
    const platform = getValues('platform');
    setValue('is_outdoor', outdoor);
    setValue('platform', outdoor ? 'outdoor' : platform === 'outdoor' ? 'other' : platform);
  };

  const addPhotos = (files: File[]) => {
    const added = files.map((file) => ({ file, previewUrl: URL.createObjectURL(file) }));
    setPhotos([...photos, ...added]);
  };

  const removePhoto = (photo: Photo) => {
    URL.revokeObjectURL(photo.previewUrl);
    setPhotos(photos.filter((item) => item !== photo));
  };

  const submit = handleSubmit((values) =>
    createAd.mutate(
      {
        text: values.text,
        platform: values.platform,
        url: values.url || undefined,
        object_id: values.object_id,
        published_at: values.published_at ? new Date(values.published_at).toISOString() : undefined,
        is_outdoor: values.is_outdoor,
        lat: values.is_outdoor && typeof values.lat === 'number' ? values.lat : undefined,
        lon: values.is_outdoor && typeof values.lon === 'number' ? values.lon : undefined,
        photos: photos.map((photo) => photo.file),
      },
      {
        onSuccess: (ad) => {
          resetAll();
          onCreated(ad.id);
          onClose();
        },
      },
    ),
  );

  return (
    <Dialog open={open} onOpenChange={(next) => !next && close()}>
      <DialogContent className="sm:max-w-xl" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{t('manual.title')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="flex flex-col gap-3">
          <TextArea
            label={t('manual.text')}
            placeholder={t('manual.textPlaceholder')}
            minRows={4}
            maxRows={10}
            required
            autoFocus
            error={errors.text?.message}
            {...register('text')}
          />
          <div className="grid grid-cols-1 items-start gap-3 sm:grid-cols-2">
            <Controller
              control={control}
              name="platform"
              render={({ field }) => (
                <SelectInput
                  label={t('manual.platform')}
                  data={options('platform', PLATFORMS)}
                  value={field.value}
                  onChange={(value) => field.onChange(parsePlatform(value) ?? 'other')}
                />
              )}
            />
            <Controller
              control={control}
              name="published_at"
              render={({ field }) => (
                <DateTimeInput
                  label={t('manual.publishedAt')}
                  placeholder={t('manual.publishedAtPlaceholder')}
                  clearable
                  value={field.value}
                  onChange={field.onChange}
                />
              )}
            />
          </div>
          <TextInput
            label={t('manual.url')}
            placeholder="https://"
            inputMode="url"
            error={errors.url?.message}
            {...register('url')}
          />
          <Controller
            control={control}
            name="object_id"
            render={({ field }) => (
              <ObjectSelect
                label={t('manual.object')}
                placeholder={t('capture.objectPlaceholder')}
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
          <SwitchInput
            label={t('manual.outdoor')}
            description={t('manual.outdoorHint')}
            checked={isOutdoor}
            onCheckedChange={setOutdoor}
          />
          {isOutdoor && (
            <PointPicker
              lat={lat}
              lon={lon}
              onChange={(nextLat, nextLon) => {
                setValue('lat', nextLat, { shouldValidate: !!errors.lat });
                setValue('lon', nextLon, { shouldValidate: !!errors.lon });
              }}
              error={errors.lat?.message ?? errors.lon?.message}
            />
          )}
          <FileInput
            label={t('manual.photos')}
            description={t('manual.photosHint')}
            placeholder={t('manual.photosPlaceholder')}
            leftSection={<IconPhoto />}
            multiple
            accept="image/*"
            value={[]}
            onChange={addPhotos}
          />
          {photos.length > 0 && (
            <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
              {photos.map((photo) => (
                <li key={photo.previewUrl} className="relative size-18">
                  <img
                    src={photo.previewUrl}
                    alt={photo.file.name}
                    className="block size-full rounded border border-border object-cover"
                  />
                  <Button
                    type="button"
                    size="icon-xs"
                    variant="secondary"
                    className="absolute top-0.5 right-0.5"
                    aria-label={t('manual.removePhoto', { name: photo.file.name })}
                    onClick={() => removePhoto(photo)}
                  >
                    <IconX />
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <DialogFooter>
            <Button type="submit" className="max-sm:min-h-11" loading={createAd.isPending}>
              {t('manual.submit')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
