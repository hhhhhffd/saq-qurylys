import { useRef, useState } from 'react';
import { ActionIcon, Button, FileInput, Group, Modal, Select, Stack, Switch, Textarea, TextInput } from '@mantine/core';
import { DateTimePicker } from '@mantine/dates';
import { useForm } from '@mantine/form';
import { IconPhoto, IconX } from '@tabler/icons-react';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { useCreateManualAd } from '@/api/hooks/ads';
import type { Platform } from '@/api/types';
import { ObjectSelect } from '@/components/ObjectSelect';
import { useEnumOptions } from '@/i18n/useEnum';
import { PLATFORMS, parsePlatform } from './constants';
import { PointPicker } from './PointPicker';
import { isHttpUrl } from './url';
import classes from './ManualAdModal.module.css';

interface FormValues {
  text: string;
  platform: Platform;
  url: string;
  object_id: number | null;
  /** `YYYY-MM-DD HH:mm:ss` from the picker, local time */
  published_at: string | null;
  is_outdoor: boolean;
  lat: number | string;
  lon: number | string;
}

interface Photo {
  file: File;
  /** object URL for the preview; revoked when the photo is removed or the form is closed */
  previewUrl: string;
}

interface Props {
  opened: boolean;
  onClose: () => void;
  onCreated: (adId: number) => void;
}

export function ManualAdModal({ opened, onClose, onCreated }: Props) {
  const { t } = useTranslation('ads');
  const options = useEnumOptions();
  const createAd = useCreateManualAd();
  const [photos, setPhotos] = useState<Photo[]>([]);
  const resetFileInput = useRef<() => void>(null);

  const required = t('required', { ns: 'common' });
  const form = useForm<FormValues>({
    initialValues: {
      text: '',
      platform: 'other',
      url: '',
      object_id: null,
      published_at: null,
      is_outdoor: false,
      lat: '',
      lon: '',
    },
    validate: {
      text: (value) => (value.trim() ? null : required),
      url: (value) => (value.trim() === '' || isHttpUrl(value.trim()) ? null : t('capture.urlInvalid')),
      lat: (value, values) => (values.is_outdoor && typeof value !== 'number' ? t('point.required') : null),
      lon: (value, values) => (values.is_outdoor && typeof value !== 'number' ? t('point.required') : null),
    },
  });

  const resetAll = () => {
    photos.forEach((photo) => URL.revokeObjectURL(photo.previewUrl));
    setPhotos([]);
    form.reset();
  };

  const close = () => {
    resetAll();
    onClose();
  };

  const setOutdoor = (isOutdoor: boolean) => {
    const platform = isOutdoor ? 'outdoor' : form.values.platform === 'outdoor' ? 'other' : form.values.platform;
    form.setValues({ is_outdoor: isOutdoor, platform });
  };

  const addPhotos = (files: File[]) => {
    const added = files.map((file) => ({ file, previewUrl: URL.createObjectURL(file) }));
    setPhotos([...photos, ...added]);
    // Lets the same file be picked again after it was removed.
    resetFileInput.current?.();
  };

  const removePhoto = (photo: Photo) => {
    URL.revokeObjectURL(photo.previewUrl);
    setPhotos(photos.filter((item) => item !== photo));
  };

  const submit = form.onSubmit((values) =>
    createAd.mutate(
      {
        text: values.text.trim(),
        platform: values.platform,
        url: values.url.trim() || undefined,
        object_id: values.object_id,
        published_at: values.published_at ? dayjs(values.published_at).toISOString() : undefined,
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
    <Modal opened={opened} onClose={close} title={t('manual.title')} size="lg">
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <Textarea
            label={t('manual.text')}
            placeholder={t('manual.textPlaceholder')}
            autosize
            minRows={4}
            maxRows={10}
            withAsterisk
            data-autofocus
            {...form.getInputProps('text')}
          />
          <Group grow align="flex-start">
            <Select
              label={t('manual.platform')}
              data={options('platform', PLATFORMS)}
              allowDeselect={false}
              value={form.values.platform}
              onChange={(value) => form.setFieldValue('platform', parsePlatform(value) ?? 'other')}
            />
            <DateTimePicker
              label={t('manual.publishedAt')}
              placeholder={t('manual.publishedAtPlaceholder')}
              valueFormat="DD.MM.YYYY HH:mm"
              clearable
              {...form.getInputProps('published_at')}
            />
          </Group>
          <TextInput label={t('manual.url')} placeholder="https://" inputMode="url" {...form.getInputProps('url')} />
          <ObjectSelect
            label={t('manual.object')}
            placeholder={t('capture.objectPlaceholder')}
            value={form.values.object_id}
            onChange={(id) => form.setFieldValue('object_id', id)}
          />
          <Switch
            label={t('manual.outdoor')}
            description={t('manual.outdoorHint')}
            checked={form.values.is_outdoor}
            onChange={(event) => setOutdoor(event.currentTarget.checked)}
          />
          {form.values.is_outdoor && (
            <PointPicker
              lat={form.values.lat}
              lon={form.values.lon}
              onChange={(lat, lon) => form.setValues({ lat, lon })}
              error={form.errors.lat ?? form.errors.lon}
            />
          )}
          <FileInput
            label={t('manual.photos')}
            description={t('manual.photosHint')}
            placeholder={t('manual.photosPlaceholder')}
            leftSection={<IconPhoto size={16} stroke={1.8} />}
            multiple
            accept="image/*"
            value={[]}
            onChange={addPhotos}
            resetRef={resetFileInput}
          />
          {photos.length > 0 && (
            <ul className={classes.previews}>
              {photos.map((photo) => (
                <li key={photo.previewUrl} className={classes.preview}>
                  <img src={photo.previewUrl} alt={photo.file.name} className={classes.image} />
                  <ActionIcon
                    size="xs"
                    variant="default"
                    className={classes.remove}
                    aria-label={t('manual.removePhoto', { name: photo.file.name })}
                    onClick={() => removePhoto(photo)}
                  >
                    <IconX size={12} stroke={2} />
                  </ActionIcon>
                </li>
              ))}
            </ul>
          )}
          <Group justify="flex-end" mt="xs">
            <Button variant="default" onClick={close}>
              {t('cancel', { ns: 'common' })}
            </Button>
            <Button type="submit" loading={createAd.isPending}>
              {t('manual.submit')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
