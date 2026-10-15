import { useMemo, useState, type ReactNode } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useSettings, useUpdateSettings } from '@/api/hooks/reference';
import type { AppSettings } from '@/api/types';
import { NumberInput } from '@/components/form/NumberInput';
import { TagsInput } from '@/components/form/TagsInput';
import { Panel } from '@/components/Panel';
import { QueryBoundary } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { useEnum } from '@/i18n/useEnum';
import { cn } from '@/lib/utils';
import { SectionHeader } from './SectionHeader';
import {
  EMAIL_PATTERN,
  NUMERIC_GROUPS,
  NUMERIC_KEYS,
  RECIPIENTS,
  numericField,
  toFormValues,
  type NumericSettingKey,
  type SettingsFormValues,
} from './settingsFields';

interface RowProps {
  /** id of the control, so the label names it */
  controlId: string;
  label: ReactNode;
  help?: ReactNode;
  error?: ReactNode;
  /** the control takes the whole row width on a narrow screen and a fixed wide column on a wide one */
  wide?: boolean;
  children: ReactNode;
}

/** A line of the settings panel: label and help on the left, the 28px control on the right. */
function SettingRow({ controlId, label, help, error, wide, children }: RowProps) {
  return (
    <div
      className={cn(
        'flex min-h-9 items-center justify-between gap-x-4 gap-y-1.5 border-b border-border px-3 py-1.5 last:border-b-0',
        wide && 'flex-col items-stretch sm:flex-row sm:items-center',
      )}
    >
      <div className="min-w-0 flex-1">
        <label htmlFor={controlId} className="text-sm text-text-2">
          {label}
        </label>
        {help && (
          <p id={`${controlId}-help`} className="text-xs text-text-3">
            {help}
          </p>
        )}
        {error && (
          <p id={`${controlId}-error`} className="text-xs text-zone-red-ink">
            {error}
          </p>
        )}
      </div>
      <div className={cn('shrink-0', wide ? 'sm:w-80' : 'w-28')}>{children}</div>
    </div>
  );
}

function SettingsForm({ settings }: { settings: AppSettings }) {
  const { t } = useTranslation('admin');
  const { t: tc } = useTranslation('common');
  const e = useEnum();
  const update = useUpdateSettings();
  // What the server holds now: the form is dirty when it differs from this, not from the first render.
  const [baseline, setBaseline] = useState(() => toFormValues(settings));

  const schema = useMemo(() => {
    const numeric = z.union([z.number(), z.string()]);
    return z
      .object({
        ...(Object.fromEntries(NUMERIC_KEYS.map((key) => [key, numeric])) as Record<NumericSettingKey, typeof numeric>),
        recipient_emails: z.object({ mio: z.array(z.string()), gask: z.array(z.string()), law_enforcement: z.array(z.string()) }),
      })
      .superRefine((values, ctx) => {
        for (const key of NUMERIC_KEYS) {
          const value = values[key];
          const { min, max, step } = numericField(key);
          let message: string | null = null;
          if (typeof value !== 'number') message = t('settings.validation.number');
          else if (step === undefined && !Number.isInteger(value)) message = t('settings.validation.integer');
          else if (value < min || value > max) message = t('settings.validation.range', { min, max });
          if (message) ctx.addIssue({ code: 'custom', path: [key], message });
        }
        const yellow = values.zone_yellow_min;
        const red = values.zone_red_min;
        if (typeof yellow === 'number' && typeof red === 'number' && yellow >= red) {
          ctx.addIssue({ code: 'custom', path: ['zone_yellow_min'], message: t('settings.validation.zoneOrder') });
        }
        for (const body of RECIPIENTS) {
          const invalid = values.recipient_emails[body].find((address) => !EMAIL_PATTERN.test(address));
          if (invalid !== undefined) {
            ctx.addIssue({ code: 'custom', path: ['recipient_emails', body], message: t('settings.validation.email', { value: invalid }) });
          }
        }
      });
  }, [t]);

  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<SettingsFormValues>({ resolver: zodResolver(schema), defaultValues: baseline });

  const values = useWatch({ control }) as SettingsFormValues;
  const changedNumbers = NUMERIC_KEYS.filter((key) => values[key] !== baseline[key]);
  const emailsChanged = RECIPIENTS.some(
    (body) => values.recipient_emails[body].join('\n') !== baseline.recipient_emails[body].join('\n'),
  );
  const dirty = changedNumbers.length > 0 || emailsChanged;

  const submit = handleSubmit((submitted) => {
    // PUT is partial on the backend: send only what the admin changed.
    const changes: Partial<AppSettings> = {};
    for (const key of changedNumbers) {
      const value = submitted[key];
      if (typeof value === 'number') changes[key] = value;
    }
    if (emailsChanged) changes.recipient_emails = submitted.recipient_emails;
    update.mutate(changes, {
      onSuccess: (saved) => {
        const next = toFormValues(saved);
        setBaseline(next);
        reset(next);
      },
    });
  });

  return (
    <form onSubmit={submit} noValidate>
      <div className="flex flex-col gap-4">
        {NUMERIC_GROUPS.map((group) => (
          <Panel key={group.id} title={t(`settings.groups.${group.id}`)} flush>
            {group.keys.map((key) => {
              const { min, max, step, decimals } = numericField(key);
              const controlId = `setting-${key}`;
              const message = errors[key]?.message;
              return (
                <SettingRow
                  key={key}
                  controlId={controlId}
                  label={e('setting', key)}
                  help={t(`settings.help.${key}`)}
                  error={message}
                >
                  <Controller
                    control={control}
                    name={key}
                    render={({ field }) => (
                      <NumberInput
                        id={controlId}
                        min={min}
                        max={max}
                        step={step}
                        allowDecimal={decimals !== undefined}
                        decimalScale={decimals}
                        value={field.value}
                        onChange={field.onChange}
                        onBlur={field.onBlur}
                        error={Boolean(message)}
                        aria-describedby={[`${controlId}-help`, message ? `${controlId}-error` : null].filter(Boolean).join(' ')}
                      />
                    )}
                  />
                </SettingRow>
              );
            })}
          </Panel>
        ))}
        <Panel title={t('settings.groups.recipients')} flush>
          <p className="border-b border-border px-3 py-2 text-xs text-text-3">{t('settings.help.recipient_emails')}</p>
          {RECIPIENTS.map((body) => {
            const controlId = `setting-recipients-${body}`;
            const message = errors.recipient_emails?.[body]?.message;
            return (
              <SettingRow key={body} controlId={controlId} label={e('recipient', body)} error={message} wide>
                <Controller
                  control={control}
                  name={`recipient_emails.${body}`}
                  render={({ field }) => (
                    <TagsInput
                      id={controlId}
                      placeholder={t('settings.recipientsPlaceholder')}
                      splitChars={[',', ';', ' ']}
                      value={field.value}
                      onChange={field.onChange}
                      error={Boolean(message)}
                    />
                  )}
                />
              </SettingRow>
            );
          })}
        </Panel>
      </div>
      <div className="sticky bottom-0 z-5 mt-4 flex flex-wrap items-center justify-between gap-3 rounded border border-border-strong bg-surface-raised px-3 py-2 shadow-2">
        <span className="text-xs text-text-2" role="status">
          {dirty ? t('settings.unsaved') : ''}
        </span>
        <div className="flex gap-2">
          <Button type="button" variant="secondary" disabled={!dirty || update.isPending} onClick={() => reset(baseline)}>
            {t('settings.revert')}
          </Button>
          <Button type="submit" disabled={!dirty} loading={update.isPending}>
            {tc('save')}
          </Button>
        </div>
      </div>
    </form>
  );
}

export function SettingsSection() {
  const { t } = useTranslation('admin');
  const query = useSettings();

  return (
    <section>
      <SectionHeader title={t('settings.title')} description={t('settings.description')} />
      <QueryBoundary query={query}>{(settings) => <SettingsForm settings={settings} />}</QueryBoundary>
    </section>
  );
}
