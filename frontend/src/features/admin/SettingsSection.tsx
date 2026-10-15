import { Button, Group, NumberInput, TagsInput } from '@mantine/core';
import { useForm, type FormErrors } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { useSettings, useUpdateSettings } from '@/api/hooks/reference';
import type { AppSettings } from '@/api/types';
import { Panel } from '@/components/Panel';
import { QueryBoundary } from '@/components/QueryState';
import { useEnum } from '@/i18n/useEnum';
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
import classes from './AdminPage.module.css';

function SettingsForm({ settings }: { settings: AppSettings }) {
  const { t } = useTranslation('admin');
  const { t: tc } = useTranslation('common');
  const e = useEnum();
  const update = useUpdateSettings();

  const numberError = (key: NumericSettingKey, value: number | string): string | null => {
    const { min, max, step } = numericField(key);
    if (typeof value !== 'number') return t('settings.validation.number');
    if (step === undefined && !Number.isInteger(value)) return t('settings.validation.integer');
    if (value < min || value > max) return t('settings.validation.range', { min, max });
    return null;
  };

  const form = useForm<SettingsFormValues>({
    initialValues: toFormValues(settings),
    validate: (values) => {
      const errors: FormErrors = {};
      for (const key of NUMERIC_KEYS) {
        const error = numberError(key, values[key]);
        if (error) errors[key] = error;
      }
      for (const body of RECIPIENTS) {
        const invalid = values.recipient_emails[body].find((address) => !EMAIL_PATTERN.test(address));
        if (invalid !== undefined) errors[`recipient_emails.${body}`] = t('settings.validation.email', { value: invalid });
      }
      return errors;
    },
  });
  const dirty = form.isDirty();

  const submit = form.onSubmit((values) => {
    // PUT is partial on the backend: send only what the admin changed.
    const changes: Partial<AppSettings> = {};
    for (const key of NUMERIC_KEYS) {
      const value = values[key];
      if (form.isDirty(key) && typeof value === 'number') changes[key] = value;
    }
    if (form.isDirty('recipient_emails')) changes.recipient_emails = values.recipient_emails;
    update.mutate(changes, {
      onSuccess: (saved) => {
        const next = toFormValues(saved);
        form.setValues(next);
        form.resetDirty(next);
      },
    });
  });

  return (
    <form onSubmit={submit} noValidate>
      <div className={classes.settingsGroups}>
        {NUMERIC_GROUPS.map((group) => (
          <Panel key={group.id} title={t(`settings.groups.${group.id}`)}>
            <div className={classes.fields}>
              {group.keys.map((key) => {
                const { min, max, step, decimals } = numericField(key);
                return (
                  <NumberInput
                    key={key}
                    label={e('setting', key)}
                    description={t(`settings.help.${key}`)}
                    min={min}
                    max={max}
                    step={step}
                    allowDecimal={decimals !== undefined}
                    decimalScale={decimals}
                    {...form.getInputProps(key)}
                  />
                );
              })}
            </div>
          </Panel>
        ))}
        <Panel title={t('settings.groups.recipients')}>
          <p className="muted">{t('settings.help.recipient_emails')}</p>
          <div className={classes.fields}>
            {RECIPIENTS.map((body) => (
              <TagsInput
                key={body}
                label={e('recipient', body)}
                placeholder={t('settings.recipientsPlaceholder')}
                splitChars={[',', ';', ' ']}
                {...form.getInputProps(`recipient_emails.${body}`)}
              />
            ))}
          </div>
        </Panel>
      </div>
      <div className={classes.settingsBar}>
        <span className="muted" role="status">
          {dirty ? t('settings.unsaved') : ''}
        </span>
        <Group gap="xs">
          <Button variant="default" disabled={!dirty || update.isPending} onClick={() => form.reset()}>
            {t('settings.revert')}
          </Button>
          <Button type="submit" disabled={!dirty} loading={update.isPending}>
            {tc('save')}
          </Button>
        </Group>
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
