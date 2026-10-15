import { useEffect, useRef, useState } from 'react';
import { ActionIcon, FileInput, Modal, NumberInput, SimpleGrid, Textarea } from '@mantine/core';
import { useForm } from '@mantine/form';
import { IconX } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useCreateInspection } from '@/api/hooks/objects';
import { CoordinateFields, DateField, FormFooter } from './fields';
import classes from './forms.module.css';
import {
  coordinateRule,
  emptyToNull,
  fileTooLarge,
  MAX_FILE_MB,
  PHOTO_ACCEPT,
  today,
  type CoordinateValue,
} from './utils';

export interface InspectionFormModalProps {
  opened: boolean;
  onClose: () => void;
  objectId: number;
}

interface InspectionFormValues {
  inspected_at: string | null;
  readiness_pct: number | string;
  lat: CoordinateValue;
  lon: CoordinateValue;
  note: string;
}

interface Photo {
  key: string;
  file: File;
  /** object URL for the preview; revoked on removal and when the form unmounts */
  url: string;
}

/** The backend rejects more photos in one inspection. */
const MAX_PHOTOS = 20;

export function InspectionFormModal({ opened, onClose, objectId }: InspectionFormModalProps) {
  const { t } = useTranslation('objectForms');
  return (
    <Modal opened={opened} onClose={onClose} title={t('inspection.createTitle')} size="lg" closeOnClickOutside={false}>
      {/* The form mounts together with the modal body, so every opening starts from fresh values. */}
      <InspectionForm objectId={objectId} onClose={onClose} />
    </Modal>
  );
}

function InspectionForm({ objectId, onClose }: Omit<InspectionFormModalProps, 'opened'>) {
  const { t } = useTranslation('objectForms');
  const { t: tc } = useTranslation('common');
  const createInspection = useCreateInspection();

  const [photos, setPhotos] = useState<Photo[]>([]);
  const [photosError, setPhotosError] = useState<string | null>(null);
  const resetPicker = useRef<() => void>(null);
  const objectUrls = useRef(new Set<string>());

  useEffect(() => {
    const urls = objectUrls.current;
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
      urls.clear();
    };
  }, []);

  const form = useForm<InspectionFormValues>({
    initialValues: { inspected_at: today(), readiness_pct: '', lat: '', lon: '', note: '' },
    validate: {
      inspected_at: (value) => (value ? null : tc('required')),
      readiness_pct: (value) =>
        typeof value === 'number' && Number.isInteger(value) && value >= 0 && value <= 100
          ? null
          : t('validation.percentRange'),
      lat: coordinateRule('lat', t),
      lon: coordinateRule('lon', t),
    },
  });

  const addPhotos = (files: File[]) => {
    // Resetting the picker reports an empty selection back here, hence the early return first.
    if (files.length === 0) return;
    // After every selection the picker is cleared so that it works as an "add photos" button.
    resetPicker.current?.();
    const known = new Set(photos.map((photo) => photo.key));
    const added: Photo[] = [];
    let error: string | null = null;
    for (const file of files) {
      const key = `${file.name}:${file.size}:${file.lastModified}`;
      if (known.has(key)) continue;
      if (fileTooLarge(file)) {
        error = t('validation.fileTooLarge', { size: MAX_FILE_MB });
      } else if (photos.length + added.length >= MAX_PHOTOS) {
        error = t('validation.tooManyPhotos', { max: MAX_PHOTOS });
      } else {
        const url = URL.createObjectURL(file);
        objectUrls.current.add(url);
        added.push({ key, file, url });
      }
    }
    setPhotosError(error);
    setPhotos([...photos, ...added]);
  };

  const removePhoto = (photo: Photo) => {
    URL.revokeObjectURL(photo.url);
    objectUrls.current.delete(photo.url);
    setPhotos(photos.filter((item) => item.key !== photo.key));
    setPhotosError(null);
  };

  const submit = (values: InspectionFormValues) => {
    if (values.inspected_at === null || typeof values.readiness_pct !== 'number') return;
    const hasPoint = typeof values.lat === 'number' && typeof values.lon === 'number';
    createInspection.mutate(
      {
        objectId,
        data: {
          inspected_at: values.inspected_at,
          readiness_pct: values.readiness_pct,
          lat: hasPoint ? Number(values.lat) : undefined,
          lon: hasPoint ? Number(values.lon) : undefined,
          note: emptyToNull(values.note) ?? undefined,
        },
        photos: photos.map((photo) => photo.file),
      },
      { onSuccess: onClose },
    );
  };

  return (
    <form onSubmit={form.onSubmit(submit)}>
      <SimpleGrid cols={{ base: 1, sm: 2 }}>
        <DateField label={t('inspection.inspectedAt')} withAsterisk {...form.getInputProps('inspected_at')} />
        <NumberInput
          label={t('inspection.readiness')}
          allowDecimal={false}
          allowNegative={false}
          hideControls
          withAsterisk
          data-autofocus
          {...form.getInputProps('readiness_pct')}
        />
        <CoordinateFields latProps={form.getInputProps('lat')} lonProps={form.getInputProps('lon')} />
        <Textarea
          className={classes.full}
          label={t('inspection.note')}
          autosize
          minRows={2}
          maxRows={6}
          {...form.getInputProps('note')}
        />
        <div className={classes.full}>
          <FileInput
            label={t('inspection.photos')}
            description={t('inspection.photosHint', { max: MAX_PHOTOS, size: MAX_FILE_MB })}
            placeholder={t('inspection.photosPlaceholder')}
            accept={PHOTO_ACCEPT}
            multiple
            value={[]}
            onChange={addPhotos}
            resetRef={resetPicker}
            error={photosError}
          />
          {photos.length > 0 && (
            <ul className={classes.thumbs}>
              {photos.map((photo) => (
                <li key={photo.key} className={classes.thumb}>
                  <img src={photo.url} alt={photo.file.name} />
                  <ActionIcon
                    className={classes.thumbRemove}
                    size="xs"
                    aria-label={t('inspection.removePhoto', { name: photo.file.name })}
                    onClick={() => removePhoto(photo)}
                  >
                    <IconX size={12} />
                  </ActionIcon>
                </li>
              ))}
            </ul>
          )}
        </div>
      </SimpleGrid>
      <FormFooter loading={createInspection.isPending} onCancel={onClose} submitLabel={tc('create')} />
    </form>
  );
}
