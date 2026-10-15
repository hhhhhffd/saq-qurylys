import { Button, Input, SegmentedControl, TextInput } from '@mantine/core';
import { DateInput } from '@mantine/dates';
import { useForm } from '@mantine/form';
import { IconPlus } from '@tabler/icons-react';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import { useCreateHoliday } from '@/api/hooks/reference';
import type { HolidayKind } from '@/api/types';
import { Panel } from '@/components/Panel';
import { useEnumOptions } from '@/i18n/useEnum';
import classes from './AdminPage.module.css';

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

  const form = useForm<FormValues>({
    initialValues: { day: null, kind: 'holiday', name: '' },
    validate: {
      day: (value) => {
        if (value === null) return tc('required');
        return existingDays.has(value) ? t('holidays.add.exists') : null;
      },
      name: (value) => (value.trim() ? null : tc('required')),
    },
  });

  const submit = form.onSubmit(({ day, kind, name }) => {
    if (day === null) return;
    create.mutate(
      { day, kind, name: name.trim() },
      {
        onSuccess: () => {
          onAdded(dayjs(day).year());
          form.reset();
        },
      },
    );
  });

  return (
    <Panel title={t('holidays.add.title')}>
      <form onSubmit={submit} noValidate className={classes.formRow}>
        <DateInput
          label={t('holidays.add.date')}
          valueFormat="DD.MM.YYYY"
          withAsterisk
          w={170}
          {...form.getInputProps('day')}
        />
        <Input.Wrapper label={t('holidays.add.kind')}>
          <SegmentedControl
            aria-label={t('holidays.add.kind')}
            data={enumOptions('holiday_kind', KINDS)}
            {...form.getInputProps('kind')}
          />
        </Input.Wrapper>
        <TextInput
          className={classes.formRowName}
          label={t('holidays.add.name')}
          placeholder={t('holidays.add.namePlaceholder')}
          withAsterisk
          autoComplete="off"
          {...form.getInputProps('name')}
        />
        <Button type="submit" leftSection={<IconPlus size={16} />} loading={create.isPending}>
          {tc('add')}
        </Button>
      </form>
    </Panel>
  );
}
