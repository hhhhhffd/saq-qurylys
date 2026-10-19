import { useEffect, useMemo, useRef, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { IconX } from '@tabler/icons-react';
import { Controller, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useCreateInspection } from '@/api/hooks/objects';
import { FileInput } from '@/components/form/FileInput';
import { NumberInput } from '@/components/form/NumberInput';
import { TextArea } from '@/components/form/TextArea';
import { Button } from '@/components/ui/button';
import { CoordinateFields, DateField, FormDialog, FormFooter, FormGrid, fullWidth } from './fields';
import {
  checkCoordinates,
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
    <FormDialog opened={opened} onClose={onClose} title={t('inspection.createTitle')}>
      <InspectionForm objectId={objectId} onClose={onClose} />
    </FormDialog>
  );
}

function InspectionForm({ objectId, onClose }: Omit<InspectionFormModalProps, 'opened'>) {
  const { t } = useTranslation('objectForms');
  const { t: tc } = useTranslation('common');
  const createInspection = useCreateInspection();

  const [photos, setPhotos] = useState<Photo[]>([]);
  const [photosError, setPhotosError] = useState<string | null>(null);
  const objectUrls = useRef(new Set<string>());

  useEffect(() => {
    const urls = objectUrls.current;
    return () => {
      urls.forEach((url) => URL.revokeObjectURL(url));
      urls.clear();
    };
  }, []);

  const schema = useMemo(
    () =>
      z
        .object({
          inspected_at: z.string().nullable().refine(Boolean, tc('required')),
          readiness_pct: z.union([z.number(), z.string()]),
          lat: z.union([z.number(), z.string()]),
          lon: z.union([z.number(), z.string()]),
          note: z.string(),
        })
        .superRefine((values, ctx) => {
          const pct = values.readiness_pct;
          if (!(typeof pct === 'number' && Number.isInteger(pct) && pct >= 0 && pct <= 100)) {
            ctx.addIssue({ code: 'custom', path: ['readiness_pct'], message: t('validation.percentRange') });
          }
          checkCoordinates(values, ctx, t);
        }),
    [t, tc],
  );

  const {
    register,
    control,
    handleSubmit,
  } = useForm<InspectionFormValues>({
    resolver: zodResolver(schema),
    defaultValues: { inspected_at: today(), readiness_pct: '', lat: '', lon: '', note: '' },
  });

  const addPhotos = (files: File[]) => {
    if (files.length === 0) return;
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
    <form onSubmit={handleSubmit(submit)} noValidate>
      <FormGrid>
        <Controller
          control={control}
          name="inspected_at"
          render={({ field, fieldState }) => (
            <DateField
              label={t('inspection.inspectedAt')}
              required
              value={field.value}
              onChange={field.onChange}
              error={fieldState.error?.message}
            />
          )}
        />
        <Controller
          control={control}
          name="readiness_pct"
          render={({ field, fieldState }) => (
            <NumberInput
              label={t('inspection.readiness')}
              allowDecimal={false}
              allowNegative={false}
              hideControls
              required
              autoFocus
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
              error={fieldState.error?.message}
            />
          )}
        />
        <CoordinateFields control={control} />
        <TextArea className={fullWidth} label={t('inspection.note')} minRows={2} maxRows={6} {...register('note')} />
        <div className={fullWidth}>
          <FileInput
            label={t('inspection.photos')}
            description={t('inspection.photosHint', { max: MAX_PHOTOS, size: MAX_FILE_MB })}
            placeholder={t('inspection.photosPlaceholder')}
            accept={PHOTO_ACCEPT}
            multiple
            value={[]}
            onChange={addPhotos}
            error={photosError}
          />
          {photos.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-2">
              {photos.map((photo) => (
                <li key={photo.key} className="relative size-18 overflow-hidden rounded-sm bg-surface-sunken shadow-1">
                  <img src={photo.url} alt={photo.file.name} className="block size-full object-cover" />
                  <Button
                    type="button"
                    variant="secondary"
                    size="icon-xs"
                    className="absolute top-0.5 right-0.5 bg-surface-glass"
                    aria-label={t('inspection.removePhoto', { name: photo.file.name })}
                    onClick={() => removePhoto(photo)}
                  >
                    <IconX />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </FormGrid>
      <FormFooter loading={createInspection.isPending} submitLabel={tc('create')} />
    </form>
  );
}
