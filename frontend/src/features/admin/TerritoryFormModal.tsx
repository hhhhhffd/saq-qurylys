import { Button, Group, Input, Modal, NumberInput, SegmentedControl, Select, Stack, Text, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { useCreateTerritory, useUpdateTerritory } from '@/api/hooks/reference';
import type { Territory, TerritoryInput, TerritoryLevel, TerritoryUpdate } from '@/api/types';
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

  const coordinateError = (value: number | string, other: number | string, min: number, max: number, rangeMessage: string) => {
    if (value === '' && other === '') return null;
    if (value === '') return t('territories.validation.coordinates');
    return typeof value === 'number' && value >= min && value <= max ? null : rangeMessage;
  };

  const form = useForm<FormValues>({
    initialValues: {
      level: territory?.level ?? 'region',
      parent: territory?.parent_id == null ? null : String(territory.parent_id),
      code: territory?.code ?? '',
      name: territory?.name ?? '',
      timezone: territory?.timezone ?? KZ_TIME_ZONES[0],
      lat: currentCenter?.lat ?? '',
      lon: currentCenter?.lon ?? '',
    },
    validate: {
      parent: (value, values) => (territory || values.level === 'region' || value ? null : tc('required')),
      code: (value) => (territory || CODE_PATTERN.test(value.trim()) ? null : t('territories.validation.code')),
      name: (value) => (value.trim() ? null : tc('required')),
      timezone: (value) => (value ? null : tc('required')),
      lat: (value, values) => coordinateError(value, values.lon, -90, 90, t('territories.validation.lat')),
      lon: (value, values) => coordinateError(value, values.lat, -180, 180, t('territories.validation.lon')),
    },
  });

  const regionOptions = territories
    .filter((item) => item.level === 'region')
    .map((item) => ({ value: String(item.id), label: item.name }));
  // A zone outside the Kazakhstan list (set by import or API) must stay selectable while editing.
  const timeZones: string[] = [...KZ_TIME_ZONES];
  if (territory && !timeZones.includes(territory.timezone)) timeZones.push(territory.timezone);

  const submit = form.onSubmit((values) => {
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
    <Modal opened onClose={onClose} title={territory ? t('territories.form.editTitle') : t('territories.form.createTitle')}>
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          {territory ? (
            <>
              <Text size="sm" c="dimmed">
                {t('territories.form.lockedHint')}
              </Text>
              <TextInput label={t('territories.form.level')} value={e('territory_level', territory.level)} disabled />
              {territory.level === 'city' && (
                <TextInput label={t('territories.form.parent')} value={parent?.name ?? '—'} disabled />
              )}
              <TextInput label={t('territories.form.code')} value={territory.code} disabled />
            </>
          ) : (
            <>
              <Input.Wrapper label={t('territories.form.level')} withAsterisk>
                <SegmentedControl
                  fullWidth
                  aria-label={t('territories.form.level')}
                  data={enumOptions('territory_level', LEVELS)}
                  {...form.getInputProps('level')}
                />
              </Input.Wrapper>
              {form.values.level === 'city' && (
                <Select
                  label={t('territories.form.parent')}
                  placeholder={t('territories.form.parentPlaceholder')}
                  data={regionOptions}
                  allowDeselect={false}
                  searchable
                  withAsterisk
                  {...form.getInputProps('parent')}
                />
              )}
              <TextInput
                label={t('territories.form.code')}
                description={t('territories.form.codeHint')}
                withAsterisk
                autoComplete="off"
                {...form.getInputProps('code')}
              />
            </>
          )}
          <TextInput label={t('territories.form.name')} withAsterisk autoComplete="off" {...form.getInputProps('name')} />
          <Select
            label={t('territories.form.timezone')}
            data={timeZones}
            allowDeselect={false}
            searchable
            withAsterisk
            {...form.getInputProps('timezone')}
          />
          <Input.Wrapper description={t('territories.form.centerHint')}>
            <Group grow align="flex-start">
              <NumberInput
                label={t('territories.form.lat')}
                decimalScale={6}
                min={-90}
                max={90}
                {...form.getInputProps('lat')}
              />
              <NumberInput
                label={t('territories.form.lon')}
                decimalScale={6}
                min={-180}
                max={180}
                {...form.getInputProps('lon')}
              />
            </Group>
          </Input.Wrapper>
          <Text size="xs" c="dimmed">
            {t('territories.form.districtsHint')}
          </Text>
          <Group justify="flex-end" mt="xs">
            <Button variant="default" onClick={onClose}>
              {tc('cancel')}
            </Button>
            <Button type="submit" loading={create.isPending || update.isPending}>
              {tc('save')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
