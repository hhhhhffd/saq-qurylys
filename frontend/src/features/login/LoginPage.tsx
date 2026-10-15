import { useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router';
import { Button, PasswordInput, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { ApiError } from '@/api/client';
import { errorMessage } from '@/api/queryClient';
import { useAuth } from '@/auth/useAuth';
import { LanguageSwitch } from '@/layout/LanguageSwitch';
import classes from './LoginPage.module.css';

export function LoginPage() {
  const { t } = useTranslation();
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const form = useForm({
    initialValues: { username: '', password: '' },
    validate: {
      username: (value) => (value.trim() ? null : t('required')),
      password: (value) => (value ? null : t('required')),
    },
  });

  if (user) return <Navigate to={(location.state as { from?: string } | null)?.from ?? '/'} replace />;

  const submit = form.onSubmit(async (values) => {
    setError(null);
    setSubmitting(true);
    try {
      await login(values.username.trim(), values.password);
      void navigate((location.state as { from?: string } | null)?.from ?? '/', { replace: true });
    } catch (err) {
      setError(err instanceof ApiError && err.status === 401 ? t('auth.invalidCredentials') : errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  });

  return (
    <div className={classes.page}>
      <div className={classes.lang}>
        <LanguageSwitch />
      </div>
      <form className={`panel ${classes.card}`} onSubmit={submit} noValidate>
        <div className={classes.brand}>
          SAQ <span>QURYLYS</span>
        </div>
        <h1 className={classes.title}>{t('auth.title')}</h1>
        <p className={classes.subtitle}>{t('auth.subtitle')}</p>
        <TextInput
          label={t('auth.username')}
          autoComplete="username"
          autoFocus
          {...form.getInputProps('username')}
        />
        <PasswordInput
          label={t('auth.password')}
          autoComplete="current-password"
          mt="md"
          {...form.getInputProps('password')}
        />
        {error && (
          <p className={classes.error} role="alert">
            {error}
          </p>
        )}
        <Button type="submit" fullWidth mt="xl" size="md" loading={submitting}>
          {t('auth.login')}
        </Button>
        <p className={classes.note}>{t('auth.internalOnly')}</p>
      </form>
    </div>
  );
}
