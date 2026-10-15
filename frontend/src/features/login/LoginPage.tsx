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
import GlitchText from '@/components/fx/GlitchText';
import { Button } from '@/components/ui/button';
import { LanguageSwitch } from '@/layout/LanguageSwitch';

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
    <div className="relative grid min-h-dvh place-items-center bg-bg px-(--gutter) py-6">
      <div className="absolute top-4 right-(--gutter)">
        <LanguageSwitch />
      </div>
      <div className="flex w-full flex-col items-center gap-8">
        <GlitchText className="font-heading text-3xl font-bold sm:text-5xl" bursts>
          SAQ QURYLYS
        </GlitchText>
        <form
          className="w-full max-w-[400px] overflow-hidden rounded-lg border border-primary/40 bg-surface"
          onSubmit={submit}
          noValidate
        >
          <div className="border-b border-border bg-surface-raised px-4 py-2">
            <h1 className="font-heading text-xs font-bold tracking-wider text-text uppercase">{t('auth.title')}</h1>
          </div>
          <div className="p-5">
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
              <p className="mt-3 text-sm text-zone-red-ink" role="alert">
                {error}
              </p>
            )}
            <Button type="submit" className="mt-5 w-full" loading={submitting}>
              {t('auth.login')}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
