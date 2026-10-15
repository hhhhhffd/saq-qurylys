import { Button, Group, Modal, Select, Stack, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { useCreateSourceAccount } from '@/api/hooks/ads';
import type { Platform, SourceAccountInput } from '@/api/types';
import { ObjectSelect } from '@/components/ObjectSelect';
import { isHttpUrl } from '@/features/ads/url';
import { useEnumOptions } from '@/i18n/useEnum';
import { aggregatorSite, SOURCE_PLATFORMS } from './collectors';
import classes from './SourcesPage.module.css';

interface FormValues {
  platform: Platform | null;
  /** channel or account (telegram, instagram) or the label of a search (aggregator) */
  handle: string;
  url: string;
  object_id: number | null;
}

export function SourceFormModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation('sources');
  const { t: tc } = useTranslation('common');
  const enumOptions = useEnumOptions();
  const create = useCreateSourceAccount();
  const form = useForm<FormValues>({
    initialValues: { platform: null, handle: '', url: '', object_id: null },
    validate: {
      platform: (value) => (value ? null : tc('required')),
      handle: (value, values) =>
        values.platform === 'aggregator' || value.trim() ? null : tc('required'),
      url: (value, values) => {
        if (values.platform !== 'aggregator') return null;
        const url = value.trim();
        if (!url) return tc('required');
        return isHttpUrl(url) && aggregatorSite(url) !== null ? null : t('form.urlInvalid');
      },
    },
  });
  const platform = form.values.platform;

  const submit = form.onSubmit((values) => {
    if (values.platform === null) return;
    // A search of an aggregator finds the listings of any seller: it is not bound to an object.
    const input: SourceAccountInput = {
      platform: values.platform,
      object_id: values.platform === 'aggregator' ? null : values.object_id,
    };
    const handle = values.handle.trim();
    if (values.platform === 'aggregator') {
      input.url = values.url.trim();
      if (handle) input.handle = handle;
    } else if (isHttpUrl(handle)) {
      // A pasted address: the server takes the name from it.
      input.url = handle;
    } else {
      input.handle = handle.replace(/^@/, '');
    }
    create.mutate(input, { onSuccess: onClose });
  });

  const handleLabel =
    platform === 'aggregator'
      ? { label: t('form.label'), description: t('form.labelHint'), placeholder: t('form.labelPlaceholder') }
      : platform === 'instagram'
        ? {
            label: t('form.instagramHandle'),
            description: t('form.instagramHandleHint'),
            placeholder: t('form.instagramHandlePlaceholder'),
          }
        : {
            label: t('form.telegramHandle'),
            description: t('form.telegramHandleHint'),
            placeholder: t('form.telegramHandlePlaceholder'),
          };

  return (
    <Modal opened onClose={onClose} title={t('form.title')} size="md">
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <Select
            label={t('form.platform')}
            data={enumOptions('platform', SOURCE_PLATFORMS)}
            allowDeselect={false}
            withAsterisk
            {...form.getInputProps('platform')}
          />
          {platform !== null && (
            <TextInput
              {...handleLabel}
              autoComplete="off"
              withAsterisk={platform !== 'aggregator'}
              {...form.getInputProps('handle')}
            />
          )}
          {platform === 'aggregator' && (
            <TextInput
              label={t('form.url')}
              description={t('form.urlHint')}
              placeholder={t('form.urlPlaceholder')}
              inputMode="url"
              autoComplete="off"
              withAsterisk
              {...form.getInputProps('url')}
            />
          )}
          {platform !== 'aggregator' && (
            <>
              <ObjectSelect
                label={t('form.object')}
                value={form.values.object_id}
                onChange={(id) => form.setFieldValue('object_id', id)}
              />
              <p className={classes.formNote}>{t('form.objectNote')}</p>
            </>
          )}
          <Group justify="flex-end" mt="xs">
            <Button variant="default" onClick={onClose}>
              {tc('cancel')}
            </Button>
            <Button type="submit" loading={create.isPending}>
              {tc('save')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
