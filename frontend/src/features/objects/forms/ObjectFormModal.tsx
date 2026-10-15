import { useState } from 'react';
import { Button, Modal, Select, SimpleGrid, TagsInput, Textarea, TextInput } from '@mantine/core';
import { useDebouncedValue, useDisclosure } from '@/lib/hooks';
import { useForm } from '@mantine/form';
import { IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { useCreateObject, useDevelopers, useUpdateObject } from '@/api/hooks/objects';
import type { ConstructionStatus, Developer, ObjectDetail, ObjectInput, Territory } from '@/api/types';
import { LoadingBlock } from '@/components/QueryState';
import { useEnumOptions } from '@/i18n/useEnum';
import { useCities, useDistrictOptions } from '@/lib/territories';
import { DeveloperFormModal } from './DeveloperFormModal';
import { CoordinateFields, DateField, FormFooter } from './fields';
import classes from './forms.module.css';
import { changedFields, coordinateRule, emptyToNull, type CoordinateValue } from './utils';

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
    <Modal
      opened={opened}
      onClose={onClose}
      title={object ? t('object.editTitle') : t('object.createTitle')}
      size="lg"
      closeOnClickOutside={false}
    >
      {/* The form mounts together with the modal body, so every opening starts from fresh values. */}
      {isPending ? <LoadingBlock /> : <ObjectForm cities={cities} object={object} onClose={onClose} />}
    </Modal>
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

  const form = useForm<ObjectFormValues>({
    initialValues: {
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
    },
    validate: {
      name: (value) => (value.trim() ? null : tc('required')),
      territory_id: (value) => (value ? null : tc('required')),
      lat: coordinateRule('lat', t),
      lon: coordinateRule('lon', t),
    },
  });

  const { districts } = useDistrictOptions(toId(form.values.territory_id));

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
    form.setFieldValue('developer_id', developer ? String(developer.id) : null);
  };

  const changeCity = (value: string | null) => {
    form.setFieldValue('territory_id', value);
    form.setFieldValue('district_id', null);
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
    const changes = changedFields(payload, toPayload(form.getInitialValues()));
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
      <form onSubmit={form.onSubmit(submit)}>
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <TextInput
            className={classes.full}
            label={t('object.name')}
            withAsterisk
            data-autofocus
            {...form.getInputProps('name')}
          />
          <TagsInput
            className={classes.full}
            label={t('object.aliases')}
            description={t('object.aliasesHint')}
            {...form.getInputProps('aliases')}
          />
          <TextInput className={classes.full} label={t('object.address')} {...form.getInputProps('address')} />
          <TextInput label={t('object.cadastralNumber')} {...form.getInputProps('cadastral_number')} />
          <TextInput label={t('object.landPurpose')} {...form.getInputProps('land_purpose')} />
          <Select
            label={t('object.city')}
            placeholder={t('object.cityPlaceholder')}
            data={cities.map((city) => ({ value: String(city.id), label: city.name }))}
            searchable
            withAsterisk
            nothingFoundMessage={tc('states.empty')}
            {...form.getInputProps('territory_id')}
            onChange={changeCity}
          />
          <Select
            label={t('object.district')}
            placeholder={t('object.districtPlaceholder')}
            data={districts.map((district) => ({ value: String(district.id), label: district.name }))}
            disabled={form.values.territory_id === null}
            searchable
            clearable
            nothingFoundMessage={tc('states.empty')}
            {...form.getInputProps('district_id')}
          />
          <div className={classes.full}>
            <Select
              label={t('object.developer')}
              placeholder={t('object.developerPlaceholder')}
              data={candidates.map((developer) => ({ value: String(developer.id), label: developerLabel(developer) }))}
              value={form.values.developer_id}
              searchable
              clearable
              // The server already filtered by the typed text.
              filter={({ options }) => options}
              nothingFoundMessage={t('object.developerNotFound')}
              onSearchChange={setDeveloperSearch}
              onChange={(value) => pickDeveloper(candidates.find((developer) => String(developer.id) === value) ?? null)}
            />
            <Button
              mt={6}
              variant="subtle"
              size="compact-sm"
              leftSection={<IconPlus size={14} />}
              onClick={developerModal.open}
            >
              {t('object.createDeveloper')}
            </Button>
          </div>
          <CoordinateFields latProps={form.getInputProps('lat')} lonProps={form.getInputProps('lon')} />
          <DateField
            label={t('object.plannedCompletion')}
            clearable
            {...form.getInputProps('planned_completion')}
          />
          <DateField
            label={t('object.forecastCompletion')}
            clearable
            {...form.getInputProps('forecast_completion')}
          />
          <Select
            label={t('object.constructionStatus')}
            data={enumOptions('construction_status', CONSTRUCTION_STATUSES)}
            allowDeselect={false}
            withAsterisk
            {...form.getInputProps('construction_status')}
          />
          {form.values.construction_status === 'stalled' && (
            <DateField label={t('object.stalledSince')} clearable {...form.getInputProps('stalled_since')} />
          )}
          <Textarea
            className={classes.full}
            label={t('object.priorViolations')}
            autosize
            minRows={2}
            maxRows={6}
            {...form.getInputProps('prior_violations')}
          />
        </SimpleGrid>
        <FormFooter loading={pending} onCancel={onClose} submitLabel={object ? tc('save') : tc('create')} />
      </form>
      {/* Outside the <form>: React submit events bubble through portals into parent forms. */}
      <DeveloperFormModal opened={developerModalOpened} onClose={developerModal.close} onSaved={pickDeveloper} />
    </>
  );
}
