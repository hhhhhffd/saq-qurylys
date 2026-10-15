import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useCreateUser, useUpdateUser } from '@/api/hooks/reference';
import type { AdminUser, Locale, Role, UserInput } from '@/api/types';
import { PasswordInput } from '@/components/form/PasswordInput';
import { SelectInput } from '@/components/form/SelectInput';
import { SwitchInput } from '@/components/form/SwitchInput';
import { TextInput } from '@/components/form/TextInput';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
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

  const schema = useMemo(
    () =>
      z.object({
        username: z
          .string()
          .refine((value) => user || USERNAME_PATTERN.test(value.trim().toLowerCase()), t('users.validation.username')),
        full_name: z.string().trim().min(1, tc('required')),
        password: z.string().superRefine((value, ctx) => {
          if (!value) {
            if (!user) ctx.addIssue({ code: 'custom', message: tc('required') });
          } else if (value.length < 8 || value.length > 128) {
            ctx.addIssue({ code: 'custom', message: t('users.validation.password') });
          }
        }),
        role: z.enum(ROLES).nullable().refine((value) => value !== null, tc('required')),
        territory: z.string().nullable().refine((value) => value, tc('required')),
        locale: z.enum(LOCALES),
        is_active: z.boolean(),
      }),
    [t, tc, user],
  );

  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      username: user?.username ?? '',
      full_name: user?.full_name ?? '',
      password: '',
      role: user?.role ?? null,
      territory: user ? (user.territory_id === null ? WHOLE_COUNTRY : String(user.territory_id)) : null,
      locale: user?.locale ?? 'ru',
      is_active: user?.is_active ?? true,
    },
  });

  const labels = territoryLabels(territories);
  const territoryOptions = [
    { value: WHOLE_COUNTRY, label: t('wholeCountry') },
    ...territories.map((territory) => ({ value: String(territory.id), label: labels.get(territory.id) ?? territory.name })),
  ];
  const localeOptions = LOCALES.map((locale) => ({ value: locale, label: t(`locales.${locale}`) }));

  const submit = handleSubmit((values) => {
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
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{user ? t('users.form.editTitle') : t('users.form.createTitle')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <TextInput
            label={t('users.form.username')}
            description={user ? t('users.form.usernameLocked') : t('users.form.usernameHint')}
            autoComplete="off"
            required={!user}
            disabled={Boolean(user)}
            error={errors.username?.message}
            {...register('username')}
          />
          <TextInput
            label={t('users.form.fullName')}
            required
            autoComplete="off"
            error={errors.full_name?.message}
            {...register('full_name')}
          />
          <PasswordInput
            label={t('users.form.password')}
            description={user ? t('users.form.passwordHintEdit') : t('users.form.passwordHintCreate')}
            required={!user}
            autoComplete="new-password"
            error={errors.password?.message}
            {...register('password')}
          />
          <Controller
            control={control}
            name="role"
            render={({ field, fieldState }) => (
              <SelectInput
                label={t('users.form.role')}
                data={enumOptions('role', ROLES)}
                required
                value={field.value}
                onChange={field.onChange}
                error={fieldState.error?.message}
              />
            )}
          />
          <Controller
            control={control}
            name="territory"
            render={({ field, fieldState }) => (
              <SelectInput
                label={t('users.form.territory')}
                data={territoryOptions}
                searchable
                required
                value={field.value}
                onChange={field.onChange}
                error={fieldState.error?.message}
              />
            )}
          />
          <Controller
            control={control}
            name="locale"
            render={({ field }) => (
              <SelectInput
                label={t('users.form.locale')}
                data={localeOptions}
                value={field.value}
                onChange={(next) => next && field.onChange(next)}
              />
            )}
          />
          <Controller
            control={control}
            name="is_active"
            render={({ field }) => (
              <SwitchInput label={t('users.form.isActive')} checked={field.value} onCheckedChange={field.onChange} />
            )}
          />
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={onClose}>
              {tc('cancel')}
            </Button>
            <Button type="submit" loading={create.isPending || update.isPending}>
              {tc('save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
