import { Button, Group, Modal, PasswordInput, Select, Stack, Switch, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { useCreateUser, useUpdateUser } from '@/api/hooks/reference';
import type { AdminUser, Locale, Role, UserInput } from '@/api/types';
import { confirmAction } from '@/lib/confirm';
import { useEnumOptions } from '@/i18n/useEnum';
import { useTerritoryList } from '@/lib/territories';
import { territoryLabels } from './territoryTree';

const ROLES: Role[] = ['admin', 'mio_officer', 'gask', 'law_enforcement'];
const LOCALES: Locale[] = ['ru', 'kk'];
/** Select values are strings, so "whole republic" (territory_id null) gets a sentinel that cannot be an id. */
const WHOLE_COUNTRY = 'all';
const USERNAME_PATTERN = /^[a-z0-9._@-]{3,64}$/;

interface FormValues {
  username: string;
  full_name: string;
  password: string;
  role: Role | null;
  territory: string | null;
  locale: Locale;
  is_active: boolean;
}

interface Props {
  /** edit mode when provided, create mode otherwise */
  user?: AdminUser;
  onClose: () => void;
}

export function UserFormModal({ user, onClose }: Props) {
  const { t } = useTranslation('admin');
  const { t: tc } = useTranslation('common');
  const enumOptions = useEnumOptions();
  const { territories } = useTerritoryList();
  const create = useCreateUser();
  const update = useUpdateUser();

  const form = useForm<FormValues>({
    initialValues: {
      username: user?.username ?? '',
      full_name: user?.full_name ?? '',
      password: '',
      role: user?.role ?? null,
      territory: user ? (user.territory_id === null ? WHOLE_COUNTRY : String(user.territory_id)) : null,
      locale: user?.locale ?? 'ru',
      is_active: user?.is_active ?? true,
    },
    validate: {
      username: (value) =>
        user || USERNAME_PATTERN.test(value.trim().toLowerCase()) ? null : t('users.validation.username'),
      full_name: (value) => (value.trim() ? null : tc('required')),
      password: (value) => {
        if (!value) return user ? null : tc('required');
        return value.length >= 8 && value.length <= 128 ? null : t('users.validation.password');
      },
      role: (value) => (value ? null : tc('required')),
      territory: (value) => (value ? null : tc('required')),
    },
  });

  const labels = territoryLabels(territories);
  const territoryOptions = [
    { value: WHOLE_COUNTRY, label: t('wholeCountry') },
    ...territories.map((territory) => ({ value: String(territory.id), label: labels.get(territory.id) ?? territory.name })),
  ];
  const localeOptions = LOCALES.map((locale) => ({ value: locale, label: t(`locales.${locale}`) }));

  const submit = form.onSubmit((values) => {
    const { role, territory } = values;
    if (role === null || territory === null) return;
    const territoryId = territory === WHOLE_COUNTRY ? null : Number(territory);
    const fullName = values.full_name.trim();

    if (!user) {
      const payload: UserInput = {
        username: values.username.trim().toLowerCase(),
        full_name: fullName,
        password: values.password,
        role,
        territory_id: territoryId,
        locale: values.locale,
        is_active: values.is_active,
      };
      create.mutate(payload, { onSuccess: onClose });
      return;
    }

    // PATCH: only changed fields; `territory_id: null` is meaningful (whole republic).
    const changes: Partial<UserInput> = {};
    if (fullName !== user.full_name) changes.full_name = fullName;
    if (role !== user.role) changes.role = role;
    if (territoryId !== user.territory_id) changes.territory_id = territoryId;
    if (values.locale !== user.locale) changes.locale = values.locale;
    if (values.is_active !== user.is_active) changes.is_active = values.is_active;
    if (values.password) changes.password = values.password;
    if (Object.keys(changes).length === 0) {
      onClose();
      return;
    }

    const save = () => update.mutate({ id: user.id, data: changes }, { onSuccess: onClose });
    if (user.is_active && !values.is_active) {
      confirmAction({
        title: t('users.deactivate.title'),
        message: t('users.deactivate.message', { name: user.full_name }),
        confirmLabel: t('users.deactivate.confirm'),
        danger: true,
        onConfirm: save,
      });
    } else {
      save();
    }
  });

  return (
    <Modal opened onClose={onClose} title={user ? t('users.form.editTitle') : t('users.form.createTitle')}>
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <TextInput
            label={t('users.form.username')}
            description={user ? t('users.form.usernameLocked') : t('users.form.usernameHint')}
            autoComplete="off"
            withAsterisk={!user}
            disabled={Boolean(user)}
            {...form.getInputProps('username')}
          />
          <TextInput
            label={t('users.form.fullName')}
            withAsterisk
            autoComplete="off"
            {...form.getInputProps('full_name')}
          />
          <PasswordInput
            label={t('users.form.password')}
            description={user ? t('users.form.passwordHintEdit') : t('users.form.passwordHintCreate')}
            withAsterisk={!user}
            autoComplete="new-password"
            {...form.getInputProps('password')}
          />
          <Select
            label={t('users.form.role')}
            data={enumOptions('role', ROLES)}
            allowDeselect={false}
            withAsterisk
            {...form.getInputProps('role')}
          />
          <Select
            label={t('users.form.territory')}
            data={territoryOptions}
            allowDeselect={false}
            searchable
            withAsterisk
            {...form.getInputProps('territory')}
          />
          <Select
            label={t('users.form.locale')}
            data={localeOptions}
            allowDeselect={false}
            {...form.getInputProps('locale')}
          />
          <Switch label={t('users.form.isActive')} {...form.getInputProps('is_active', { type: 'checkbox' })} />
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
