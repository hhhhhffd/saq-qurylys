import { useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { Navigate, useLocation, useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { ApiError } from '@/api/client';
import { errorMessage } from '@/api/queryClient';
import { useAuth } from '@/auth/useAuth';
import { PasswordInput } from '@/components/form/PasswordInput';
import { TextInput } from '@/components/form/TextInput';
import { Button } from '@/components/ui/button';
import { LanguageSwitch } from '@/layout/LanguageSwitch';
import classes from './LoginPage.module.css';

export function LoginPage() {
  const { t } = useTranslation();
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // The schema is built with `t`, so its messages are translated; zod reports them as the field errors.
  const schema = useMemo(
    () => z.object({ username: z.string().trim().min(1, t('required')), password: z.string().min(1, t('required')) }),
    [t],
  );
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm({ resolver: zodResolver(schema), defaultValues: { username: '', password: '' } });

  if (user) return <Navigate to={(location.state as { from?: string } | null)?.from ?? '/'} replace />;

  const submit = handleSubmit(async (values) => {
    setError(null);
    setSubmitting(true);
    try {
      await login(values.username, values.password);
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
        <div className="flex flex-col gap-3">
          <TextInput label={t('auth.username')} autoComplete="username" autoFocus error={errors.username?.message} {...register('username')} />
          <PasswordInput
            label={t('auth.password')}
            autoComplete="current-password"
            error={errors.password?.message}
            {...register('password')}
          />
        </div>
        {error && (
          <p className={classes.error} role="alert">
            {error}
          </p>
        )}
        <Button type="submit" className="mt-6 w-full" loading={submitting}>
          {t('auth.login')}
        </Button>
        <p className={classes.note}>{t('auth.internalOnly')}</p>
      </form>
    </div>
  );
}
