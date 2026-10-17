import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { z } from 'zod';
import { useCreateVisionSession } from '@/api/hooks/vision';
import type { VisionSource } from '@/api/types';
import { DateTimeInput } from '@/components/form/DateTimeInput';
import { SelectInput } from '@/components/form/SelectInput';
import { TextArea } from '@/components/form/TextArea';
import { ObjectSelect } from '@/components/ObjectSelect';
import { Button } from '@/components/ui/button';
import { DialogFooter } from '@/components/ui/dialog';
import { FormDialog } from '@/features/objects/forms/fields';
import { useEnumOptions } from '@/i18n/useEnum';
import { SOURCES, isSource } from './constants';

interface Props {
  opened: boolean;
  onClose: () => void;
  /** the object card opens the dialog with its own object chosen */
  defaultObjectId?: number | null;
}

export function NewSessionDialog({ opened, onClose, defaultObjectId = null }: Props) {
  const { t } = useTranslation('vision');
  const { t: tc } = useTranslation();
  const options = useEnumOptions();
  const navigate = useNavigate();
  const create = useCreateVisionSession();

  const schema = useMemo(
    () =>
      z.object({
        object_id: z.number().nullable(),
        source: z.custom<VisionSource>(),
        captured_at: z.string().nullable(),
        note: z.string().trim(),
      }),
    [],
  );
  const { control, register, handleSubmit } = useForm({
    resolver: zodResolver(schema),
    defaultValues: {
      object_id: defaultObjectId,
      source: 'drone' as VisionSource,
      captured_at: null as string | null,
      note: '',
    },
  });

  const submit = handleSubmit((values) =>
    create.mutate(
      {
        object_id: values.object_id,
        source: values.source,
        captured_at: values.captured_at ? new Date(values.captured_at).toISOString() : null,
        note: values.note || null,
      },
      {
        onSuccess: (session) => {
          onClose();
          void navigate(`/vision/${session.id}`);
        },
      },
    ),
  );

  return (
    <FormDialog opened={opened} onClose={onClose} title={t('new.title')}>
      <form onSubmit={submit} noValidate className="flex flex-col gap-3">
        <Controller
          control={control}
          name="object_id"
          render={({ field }) => (
            <ObjectSelect
              label={t('new.object')}
              description={t('new.objectHint')}
              placeholder={t('new.objectPlaceholder')}
              value={field.value}
              onChange={field.onChange}
            />
          )}
        />
        <div className="grid items-start gap-3 sm:grid-cols-2">
          <Controller
            control={control}
            name="source"
            render={({ field }) => (
              <SelectInput
                label={t('new.source')}
                data={options('vision_source', SOURCES)}
                value={field.value}
                onChange={(value) => field.onChange(isSource(value) ? value : 'other')}
              />
            )}
          />
          <Controller
            control={control}
            name="captured_at"
            render={({ field }) => (
              <DateTimeInput
                label={t('new.capturedAt')}
                placeholder={t('new.capturedAtPlaceholder')}
                clearable
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
        </div>
        <TextArea label={t('new.note')} minRows={2} maxRows={6} {...register('note')} />
        <DialogFooter>
          <Button type="button" variant="secondary" onClick={onClose}>
            {tc('cancel')}
          </Button>
          <Button type="submit" loading={create.isPending}>
            {t('new.submit')}
          </Button>
        </DialogFooter>
      </form>
    </FormDialog>
  );
}
