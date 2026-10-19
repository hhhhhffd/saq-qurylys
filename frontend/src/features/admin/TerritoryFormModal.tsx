import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useCreateTerritory, useUpdateTerritory } from '@/api/hooks/reference';
import type { Territory, TerritoryInput, TerritoryLevel, TerritoryUpdate } from '@/api/types';
import { NumberInput } from '@/components/form/NumberInput';
import { SelectInput } from '@/components/form/SelectInput';
import { TextInput } from '@/components/form/TextInput';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { useEnum, useEnumOptions } from '@/i18n/useEnum';
import { toLatLon } from '@/lib/geo';
import { useTerritoryList } from '@/lib/territories';
import { KZ_TIME_ZONES } from './territoryTree';

const LEVELS: TerritoryLevel[] = ['region', 'city'];
const CODE_PATTERN = /^[a-z0-9][a-z0-9-]{1,63}$/;

interface FormValues {
  level: TerritoryLevel;
  parent: string | null;
  code: string;
  name: string;
  timezone: string;
  /** number, or '' while empty */
  lat: number | string;
  lon: number | string;
}

interface Props {
  /** edit mode when provided, create mode otherwise */
  territory?: Territory;
  onClose: () => void;
}

export function TerritoryFormModal({ territory, onClose }: Props) {
  const { t } = useTranslation('admin');
  const { t: tc } = useTranslation('common');
  const e = useEnum();
  const enumOptions = useEnumOptions();
  const { territories } = useTerritoryList();
  const create = useCreateTerritory();
  const update = useUpdateTerritory();

  const currentCenter = territory ? toLatLon(territory) : null;
  const parent = territory?.parent_id == null ? undefined : territories.find((item) => item.id === territory.parent_id);

  const schema = useMemo(() => {
    const coordinateIssue = (
      ctx: z.RefinementCtx,
      path: 'lat' | 'lon',
      value: number | string,
      other: number | string,
      min: number,
      max: number,
      rangeMessage: string,
    ) => {
      if (value === '' && other === '') return;
      if (value === '') ctx.addIssue({ code: 'custom', path: [path], message: t('territories.validation.coordinates') });
      else if (!(typeof value === 'number' && value >= min && value <= max)) {
        ctx.addIssue({ code: 'custom', path: [path], message: rangeMessage });
      }
    };
    return z
      .object({
        level: z.enum(LEVELS),
        parent: z.string().nullable(),
        code: z.string(),
        name: z.string().trim().min(1, tc('required')),
        timezone: z.string().min(1, tc('required')),
        lat: z.union([z.number(), z.string()]),
        lon: z.union([z.number(), z.string()]),
      })
      .superRefine((values, ctx) => {
        if (!territory) {
          if (values.level === 'city' && !values.parent) ctx.addIssue({ code: 'custom', path: ['parent'], message: tc('required') });
          if (!CODE_PATTERN.test(values.code.trim())) {
            ctx.addIssue({ code: 'custom', path: ['code'], message: t('territories.validation.code') });
          }
        }
        coordinateIssue(ctx, 'lat', values.lat, values.lon, -90, 90, t('territories.validation.lat'));
        coordinateIssue(ctx, 'lon', values.lon, values.lat, -180, 180, t('territories.validation.lon'));
      });
  }, [t, tc, territory]);

  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      level: territory?.level ?? 'region',
      parent: territory?.parent_id == null ? null : String(territory.parent_id),
      code: territory?.code ?? '',
      name: territory?.name ?? '',
      timezone: territory?.timezone ?? KZ_TIME_ZONES[0],
      lat: currentCenter?.lat ?? '',
      lon: currentCenter?.lon ?? '',
    },
  });
  const level = useWatch({ control, name: 'level' });

  const regionOptions = territories
    .filter((item) => item.level === 'region')
    .map((item) => ({ value: String(item.id), label: item.name }));
  // A zone outside the Kazakhstan list (set by import or API) must stay selectable while editing.
  const timeZones: string[] = [...KZ_TIME_ZONES];
  if (territory && !timeZones.includes(territory.timezone)) timeZones.push(territory.timezone);
  const timeZoneOptions = timeZones.map((zone) => ({ value: zone, label: zone }));

  const submit = handleSubmit((values) => {
    const name = values.name.trim();
    const { lat, lon } = values;
    const hasCenter = typeof lat === 'number' && typeof lon === 'number';

    if (!territory) {
      const payload: TerritoryInput = {
        parent_id: values.level === 'city' && values.parent ? Number(values.parent) : null,
        level: values.level,
        code: values.code.trim(),
        name,
        timezone: values.timezone,
        ...(hasCenter && { lat, lon }),
      };
      create.mutate(payload, { onSuccess: onClose });
      return;
    }

    // PATCH accepts only name, time zone and the center; an empty center cannot be cleared, so it is not sent.
    const changes: TerritoryUpdate = {};
    if (name !== territory.name) changes.name = name;
    if (values.timezone !== territory.timezone) changes.timezone = values.timezone;
    if (hasCenter && (lat !== currentCenter?.lat || lon !== currentCenter?.lon)) {
      changes.lat = lat;
      changes.lon = lon;
    }
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    update.mutate({ id: territory.id, data: changes }, { onSuccess: onClose });
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{territory ? t('territories.form.editTitle') : t('territories.form.createTitle')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="grid gap-3">
          {territory ? (
            <>
              <p className="text-sm text-text-2">{t('territories.form.lockedHint')}</p>
              <TextInput label={t('territories.form.level')} value={e('territory_level', territory.level)} disabled readOnly />
              {territory.level === 'city' && (
                <TextInput label={t('territories.form.parent')} value={parent?.name ?? '—'} disabled readOnly />
              )}
              <TextInput label={t('territories.form.code')} value={territory.code} disabled readOnly />
            </>
          ) : (
            <>
              <Field>
                <FieldLabel>
                  {t('territories.form.level')}
                  <span aria-hidden className="text-accent-text">
                    {' *'}
                  </span>
                </FieldLabel>
                <Controller
                  control={control}
                  name="level"
                  render={({ field }) => (
                    <ToggleGroup
                      type="single"
                      className="w-full"
                      aria-label={t('territories.form.level')}
                      value={field.value}
                      onValueChange={(next) => next && field.onChange(next)}
                    >
                      {enumOptions('territory_level', LEVELS).map((option) => (
                        <ToggleGroupItem key={option.value} value={option.value} className="flex-1">
                          {option.label}
                        </ToggleGroupItem>
                      ))}
                    </ToggleGroup>
                  )}
                />
              </Field>
              {level === 'city' && (
                <Controller
                  control={control}
                  name="parent"
                  render={({ field, fieldState }) => (
                    <SelectInput
                      label={t('territories.form.parent')}
                      placeholder={t('territories.form.parentPlaceholder')}
                      data={regionOptions}
                      searchable
                      required
                      value={field.value}
                      onChange={field.onChange}
                      error={fieldState.error?.message}
                    />
                  )}
                />
              )}
              <TextInput
                label={t('territories.form.code')}
                description={t('territories.form.codeHint')}
                required
                autoComplete="off"
                error={errors.code?.message}
                {...register('code')}
              />
            </>
          )}
          <TextInput label={t('territories.form.name')} required autoComplete="off" error={errors.name?.message} {...register('name')} />
          <Controller
            control={control}
            name="timezone"
            render={({ field, fieldState }) => (
              <SelectInput
                label={t('territories.form.timezone')}
                data={timeZoneOptions}
                searchable
                required
                value={field.value}
                onChange={field.onChange}
                error={fieldState.error?.message}
              />
            )}
          />
          <Field>
            <FieldDescription>{t('territories.form.centerHint')}</FieldDescription>
            <div className="grid grid-cols-2 items-start gap-3">
              <Controller
                control={control}
                name="lat"
                render={({ field, fieldState }) => (
                  <NumberInput
                    label={t('territories.form.lat')}
                    decimalScale={6}
                    min={-90}
                    max={90}
                    value={field.value}
                    onChange={field.onChange}
                    error={fieldState.error?.message}
                  />
                )}
              />
              <Controller
                control={control}
                name="lon"
                render={({ field, fieldState }) => (
                  <NumberInput
                    label={t('territories.form.lon')}
                    decimalScale={6}
                    min={-180}
                    max={180}
                    value={field.value}
                    onChange={field.onChange}
                    error={fieldState.error?.message}
                  />
                )}
              />
            </div>
          </Field>
          <p className="text-xs text-text-3">{t('territories.form.districtsHint')}</p>
          <DialogFooter>
            <Button type="submit" loading={create.isPending || update.isPending}>
              {tc('save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
