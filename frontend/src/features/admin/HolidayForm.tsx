import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { IconPlus } from '@tabler/icons-react';
import dayjs from 'dayjs';
import { Controller, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useCreateHoliday } from '@/api/hooks/reference';
import type { HolidayKind } from '@/api/types';
import { DateInput } from '@/components/form/DateInput';
import { TextInput } from '@/components/form/TextInput';
import { Panel } from '@/components/Panel';
import { Button } from '@/components/ui/button';
import { Field, FieldLabel } from '@/components/ui/field';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { useEnumOptions } from '@/i18n/useEnum';

const KINDS: HolidayKind[] = ['holiday', 'workday'];

interface FormValues {
  /** `YYYY-MM-DD` (DateInput value) */
  day: string | null;
  kind: HolidayKind;
  name: string;
}

interface Props {
  existingDays: Set<string>;
  /** called with the year of the added day, so the table can show it */
  onAdded: (year: number) => void;
}

export function HolidayForm({ existingDays, onAdded }: Props) {
  const { t } = useTranslation('admin');
  const { t: tc } = useTranslation('common');
  const enumOptions = useEnumOptions();
  const create = useCreateHoliday();

  const schema = useMemo(
    () =>
      z.object({
        day: z
          .string()
          .nullable()
          .superRefine((value, ctx) => {
            if (value === null) ctx.addIssue({ code: 'custom', message: tc('required') });
            else if (existingDays.has(value)) ctx.addIssue({ code: 'custom', message: t('holidays.add.exists') });
          }),
        kind: z.enum(KINDS),
        name: z.string().trim().min(1, tc('required')),
      }),
    [t, tc, existingDays],
  );

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { day: null, kind: 'holiday', name: '' } });

  const submit = handleSubmit(({ day, kind, name }) => {
    if (day === null) return;
    create.mutate(
      { day, kind, name: name.trim() },
      {
        onSuccess: () => {
          onAdded(dayjs(day).year());
          reset();
        },
      },
    );
  });

  return (
    <Panel title={t('holidays.add.title')}>
      <form onSubmit={submit} noValidate className="flex flex-wrap items-start gap-3">
        <Controller
          control={control}
          name="day"
          render={({ field, fieldState }) => (
            <DateInput
              label={t('holidays.add.date')}
              required
              className="w-44"
              value={field.value}
              onChange={field.onChange}
              error={fieldState.error?.message}
            />
          )}
        />
        <Field className="w-auto">
          <FieldLabel id="holiday-kind-label">{t('holidays.add.kind')}</FieldLabel>
          <Controller
            control={control}
            name="kind"
            render={({ field }) => (
              <ToggleGroup
                type="single"
                aria-label={t('holidays.add.kind')}
                value={field.value}
                onValueChange={(next) => next && field.onChange(next)}
              >
                {enumOptions('holiday_kind', KINDS).map((option) => (
                  <ToggleGroupItem key={option.value} value={option.value}>
                    {option.label}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            )}
          />
        </Field>
        <TextInput
          className="min-w-60 flex-1"
          label={t('holidays.add.name')}
          placeholder={t('holidays.add.namePlaceholder')}
          required
          autoComplete="off"
          error={errors.name?.message}
          {...register('name')}
        />
        <Button type="submit" loading={create.isPending} className="self-end">
          <IconPlus />
          {tc('add')}
        </Button>
      </form>
    </Panel>
  );
}
