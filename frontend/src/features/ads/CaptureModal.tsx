import { Button, Group, Modal, Select, Stack, Text, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { useCaptureAd } from '@/api/hooks/ads';
import type { Platform } from '@/api/types';
import { ObjectSelect } from '@/components/ObjectSelect';
import { useEnumOptions } from '@/i18n/useEnum';
import { CAPTURE_PLATFORMS, parsePlatform } from './constants';
import { isHttpUrl } from './url';

interface FormValues {
  url: string;
  object_id: number | null;
  platform: Platform | null;
}

interface Props {
  opened: boolean;
  onClose: () => void;
  /** called with the id of the new publication (its capture is still pending) */
  onCreated: (adId: number) => void;
}

export function CaptureModal({ opened, onClose, onCreated }: Props) {
  const { t } = useTranslation('ads');
  const options = useEnumOptions();
  const captureAd = useCaptureAd();
  const form = useForm<FormValues>({
    initialValues: { url: '', object_id: null, platform: null },
    validate: {
      url: (value) => {
        const url = value.trim();
        if (!url) return t('required', { ns: 'common' });
        return isHttpUrl(url) ? null : t('capture.urlInvalid');
      },
    },
  });

  const close = () => {
    form.reset();
    onClose();
  };

  const submit = form.onSubmit((values) =>
    captureAd.mutate(
      { url: values.url.trim(), object_id: values.object_id, platform: values.platform ?? undefined },
      {
        onSuccess: (ad) => {
          form.reset();
          onCreated(ad.id);
          onClose();
        },
      },
    ),
  );

  return (
    <Modal opened={opened} onClose={close} title={t('capture.title')} size="md">
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <Text size="sm" c="dimmed">
            {t('capture.hint')}
          </Text>
          <TextInput
            label={t('capture.url')}
            placeholder="https://"
            inputMode="url"
            withAsterisk
            data-autofocus
            {...form.getInputProps('url')}
          />
          <ObjectSelect
            label={t('capture.object')}
            placeholder={t('capture.objectPlaceholder')}
            value={form.values.object_id}
            onChange={(id) => form.setFieldValue('object_id', id)}
          />
          <Select
            label={t('capture.platform')}
            description={t('capture.platformHint')}
            data={options('platform', CAPTURE_PLATFORMS)}
            value={form.values.platform}
            onChange={(value) => form.setFieldValue('platform', parsePlatform(value))}
            clearable
          />
          <Group justify="flex-end" mt="xs">
            <Button variant="default" onClick={close}>
              {t('cancel', { ns: 'common' })}
            </Button>
            <Button type="submit" loading={captureAd.isPending}>
              {t('capture.submit')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
