import { useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { IconPlus } from '@tabler/icons-react';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { z } from 'zod';
import { useCreateObject, useDevelopers, useUpdateObject } from '@/api/hooks/objects';
import type { ConstructionStatus, Developer, ObjectDetail, ObjectInput, Territory } from '@/api/types';
import { LoadingBlock } from '@/components/QueryState';
import { SelectInput } from '@/components/form/SelectInput';
import { TagsInput } from '@/components/form/TagsInput';
import { TextArea } from '@/components/form/TextArea';
import { TextInput } from '@/components/form/TextInput';
import { Button } from '@/components/ui/button';
import { useEnumOptions } from '@/i18n/useEnum';
import { useDebouncedValue, useDisclosure } from '@/lib/hooks';
import { useCities, useDistrictOptions } from '@/lib/territories';
import { DeveloperFormModal } from './DeveloperFormModal';
import { CoordinateFields, DateField, FormDialog, FormFooter, FormGrid, fullWidth } from './fields';
import { changedFields, checkCoordinates, emptyToNull, type CoordinateValue } from './utils';

export interface ObjectFormModalProps {
  opened: boolean;
  onClose: () => void;
  /** edit mode when provided, create mode otherwise */
  object?: ObjectDetail;
}

interface ObjectFormValues {
  name: string;
  aliases: string[];
  address: string;
  cadastral_number: string;
  land_purpose: string;
  territory_id: string | null;
  district_id: string | null;
  developer_id: string | null;
  lat: CoordinateValue;
  lon: CoordinateValue;
  planned_completion: string | null;
  forecast_completion: string | null;
  construction_status: ConstructionStatus;
  stalled_since: string | null;
  prior_violations: string;
}

const CONSTRUCTION_STATUSES: ConstructionStatus[] = ['not_started', 'active', 'stalled', 'completed'];

function developerLabel(developer: Developer): string {
  return `${developer.name} (${developer.bin})`;
}

function toId(value: string | null): number | null {
  return value ? Number(value) : null;
}

function toPayload(values: ObjectFormValues): ObjectInput {
  const { lat, lon } = values;
  const hasPoint = typeof lat === 'number' && typeof lon === 'number';
  return {
    name: values.name.trim(),
    territory_id: Number(values.territory_id),
    district_id: toId(values.district_id),
    developer_id: toId(values.developer_id),
    aliases: values.aliases,
    address: emptyToNull(values.address),
    cadastral_number: emptyToNull(values.cadastral_number),
    land_purpose: emptyToNull(values.land_purpose),
    lat: hasPoint ? lat : null,
    lon: hasPoint ? lon : null,
    planned_completion: values.planned_completion,
    forecast_completion: values.forecast_completion,
    construction_status: values.construction_status,
    stalled_since: values.construction_status === 'stalled' ? values.stalled_since : null,
    prior_violations: emptyToNull(values.prior_violations),
  };
}

export function ObjectFormModal({ opened, onClose, object }: ObjectFormModalProps) {
  const { t } = useTranslation('objectForms');
  const { cities, isPending } = useCities();
  return (
    <FormDialog opened={opened} onClose={onClose} title={object ? t('object.editTitle') : t('object.createTitle')}>
      {isPending ? <LoadingBlock /> : <ObjectForm cities={cities} object={object} onClose={onClose} />}
    </FormDialog>
  );
}

interface ObjectFormProps {
  cities: Territory[];
  object?: ObjectDetail;
  onClose: () => void;
}

function ObjectForm({ cities, object, onClose }: ObjectFormProps) {
  const { t } = useTranslation('objectForms');
  const { t: tc } = useTranslation('common');
  const enumOptions = useEnumOptions();
  const navigate = useNavigate();
  const createObject = useCreateObject();
  const updateObject = useUpdateObject();
  const pending = createObject.isPending || updateObject.isPending;
  const [developerModalOpened, developerModal] = useDisclosure(false);

  const [initialValues] = useState<ObjectFormValues>(() => ({
    name: object?.name ?? '',
    aliases: object?.aliases ?? [],
    address: object?.address ?? '',
    cadastral_number: object?.cadastral_number ?? '',
    land_purpose: object?.land_purpose ?? '',
    // A user who sees a single city has nothing to choose.
    territory_id: object ? String(object.territory_id) : cities.length === 1 ? String(cities[0].id) : null,
    district_id: object?.district_id != null ? String(object.district_id) : null,
    developer_id: object?.developer_id != null ? String(object.developer_id) : null,
    lat: object?.lat ?? '',
    lon: object?.lon ?? '',
    planned_completion: object?.planned_completion ?? null,
    forecast_completion: object?.forecast_completion ?? null,
    construction_status: object?.construction_status ?? 'active',
    stalled_since: object?.stalled_since ?? null,
    prior_violations: object?.prior_violations ?? '',
  }));

  const schema = useMemo(
    () =>
      z
        .object({
          name: z.string().trim().min(1, tc('required')),
          aliases: z.array(z.string()),
          address: z.string(),
          cadastral_number: z.string(),
          land_purpose: z.string(),
          territory_id: z.string().nullable().refine(Boolean, tc('required')),
          district_id: z.string().nullable(),
          developer_id: z.string().nullable(),
          lat: z.union([z.number(), z.string()]),
          lon: z.union([z.number(), z.string()]),
          planned_completion: z.string().nullable(),
          forecast_completion: z.string().nullable(),
          construction_status: z.custom<ConstructionStatus>(),
          stalled_since: z.string().nullable(),
          prior_violations: z.string(),
        })
        .superRefine((values, ctx) => checkCoordinates(values, ctx, t)),
    [t, tc],
  );

  const {
    register,
    control,
    handleSubmit,
    setValue,
    formState: { errors },
  } = useForm<ObjectFormValues>({ resolver: zodResolver(schema), defaultValues: initialValues });

  const territoryId = useWatch({ control, name: 'territory_id' });
  const constructionStatus = useWatch({ control, name: 'construction_status' });
  const { districts } = useDistrictOptions(toId(territoryId));

  // Developer search is server-side; the selected developer is kept so its label survives new searches.
  const [selectedDeveloper, setSelectedDeveloper] = useState<Developer | null>(object?.developer ?? null);
  const [developerSearch, setDeveloperSearch] = useState('');
  const [debouncedSearch] = useDebouncedValue(developerSearch, 300);
  const selectedLabel = selectedDeveloper ? developerLabel(selectedDeveloper) : '';
  const found = useDevelopers(debouncedSearch === selectedLabel ? '' : debouncedSearch).data ?? [];
  const candidates =
    selectedDeveloper && !found.some((developer) => developer.id === selectedDeveloper.id)
      ? [selectedDeveloper, ...found]
      : found;

  const pickDeveloper = (developer: Developer | null) => {
    setSelectedDeveloper(developer);
    setValue('developer_id', developer ? String(developer.id) : null);
  };

  const submit = (values: ObjectFormValues) => {
    const payload = toPayload(values);
    if (!object) {
      createObject.mutate(payload, {
        onSuccess: (created) => {
          onClose();
          void navigate(`/objects/${created.id}`);
        },
      });
      return;
    }
    const changes = changedFields(payload, toPayload(initialValues));
    if ('lat' in changes || 'lon' in changes) {
      // The backend rejects a lone lat or lon.
      changes.lat = payload.lat;
      changes.lon = payload.lon;
    }
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }
    updateObject.mutate({ id: object.id, data: changes }, { onSuccess: onClose });
  };

  return (
    <>
      <form onSubmit={handleSubmit(submit)} noValidate>
        <FormGrid>
          <TextInput
            className={fullWidth}
            label={t('object.name')}
            required
            error={errors.name?.message}
            {...register('name')}
          />
          <Controller
            control={control}
            name="aliases"
            render={({ field }) => (
              <TagsInput
                className={fullWidth}
                label={t('object.aliases')}
                description={t('object.aliasesHint')}
                value={field.value}
                onChange={field.onChange}
                onBlur={field.onBlur}
              />
            )}
          />
          <TextInput className={fullWidth} label={t('object.address')} {...register('address')} />
          <TextInput label={t('object.cadastralNumber')} {...register('cadastral_number')} />
          <TextInput label={t('object.landPurpose')} {...register('land_purpose')} />
          <Controller
            control={control}
            name="territory_id"
            render={({ field, fieldState }) => (
              <SelectInput
                label={t('object.city')}
                placeholder={t('object.cityPlaceholder')}
                data={cities.map((city) => ({ value: String(city.id), label: city.name }))}
                searchable
                required
                nothingFound={tc('states.empty')}
                value={field.value}
                onChange={(value) => {
                  field.onChange(value);
                  setValue('district_id', null);
                }}
                error={fieldState.error?.message}
              />
            )}
          />
          <Controller
            control={control}
            name="district_id"
            render={({ field }) => (
              <SelectInput
                label={t('object.district')}
                placeholder={t('object.districtPlaceholder')}
                data={districts.map((district) => ({ value: String(district.id), label: district.name }))}
                disabled={territoryId === null}
                searchable
                clearable
                nothingFound={tc('states.empty')}
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
          <div className={fullWidth}>
            <Controller
              control={control}
              name="developer_id"
              render={({ field }) => (
                <SelectInput
                  label={t('object.developer')}
                  placeholder={t('object.developerPlaceholder')}
                  data={candidates.map((developer) => ({ value: String(developer.id), label: developerLabel(developer) }))}
                  value={field.value}
                  clearable
                  nothingFound={t('object.developerNotFound')}
                  onSearchChange={setDeveloperSearch}
                  onChange={(value) => pickDeveloper(candidates.find((developer) => String(developer.id) === value) ?? null)}
                />
              )}
            />
            <Button type="button" className="mt-1.5" variant="ghost" size="sm" onClick={developerModal.open}>
              <IconPlus />
              {t('object.createDeveloper')}
            </Button>
          </div>
          <CoordinateFields control={control} />
          <Controller
            control={control}
            name="planned_completion"
            render={({ field }) => (
              <DateField label={t('object.plannedCompletion')} clearable value={field.value} onChange={field.onChange} />
            )}
          />
          <Controller
            control={control}
            name="forecast_completion"
            render={({ field }) => (
              <DateField label={t('object.forecastCompletion')} clearable value={field.value} onChange={field.onChange} />
            )}
          />
          <Controller
            control={control}
            name="construction_status"
            render={({ field }) => (
              <SelectInput
                label={t('object.constructionStatus')}
                data={enumOptions('construction_status', CONSTRUCTION_STATUSES)}
                required
                value={field.value}
                onChange={(value) => value && field.onChange(value)}
              />
            )}
          />
          {constructionStatus === 'stalled' && (
            <Controller
              control={control}
              name="stalled_since"
              render={({ field }) => (
                <DateField label={t('object.stalledSince')} clearable value={field.value} onChange={field.onChange} />
              )}
            />
          )}
          <TextArea
            className={fullWidth}
            label={t('object.priorViolations')}
            minRows={2}
            maxRows={6}
            {...register('prior_violations')}
          />
        </FormGrid>
        <FormFooter loading={pending} submitLabel={object ? tc('save') : tc('create')} />
      </form>
      {/* Outside the <form>: React submit events bubble through portals into parent forms. */}
      <DeveloperFormModal opened={developerModalOpened} onClose={developerModal.close} onSaved={pickDeveloper} />
    </>
  );
}
