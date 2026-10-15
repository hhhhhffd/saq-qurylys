import { Button, Group, Modal, Stack, Textarea } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { useRespondSignal } from '@/api/hooks/signals';
import type { SignalDetail } from '@/api/types';
import { MIN_RESPONSE_TEXT } from './constants';
import { useApplySignal } from './useApplySignal';

interface Props {
  opened: boolean;
  onClose: () => void;
  detail: SignalDetail;
}

export function ResponseModal({ opened, onClose, detail }: Props) {
  const { t } = useTranslation('signals');
  const { t: tc } = useTranslation();
  const respond = useRespondSignal();
  const apply = useApplySignal();
  const form = useForm({
    initialValues: { response: '' },
    validate: {
      response: (value) => (value.trim().length < MIN_RESPONSE_TEXT ? t('respond.tooShort', { count: MIN_RESPONSE_TEXT }) : null),
    },
  });

  const close = () => {
    form.reset();
    onClose();
  };

  const submit = form.onSubmit((values) =>
    respond.mutate(
      { id: detail.id, response_text: values.response.trim() },
      {
        onSuccess: (next) => {
          apply(next);
          close();
        },
      },
    ),
  );

  return (
    <Modal opened={opened} onClose={close} title={t('actions.respond')}>
      <form onSubmit={submit}>
        <Stack gap="md">
          <Textarea
            label={t('respond.label')}
            description={t('respond.description', { number: detail.number })}
            placeholder={t('respond.placeholder')}
            withAsterisk
            autosize
            minRows={5}
            maxRows={12}
            data-autofocus
            {...form.getInputProps('response')}
          />
          <Group justify="flex-end" gap="sm">
            <Button variant="default" onClick={close} disabled={respond.isPending}>
              {tc('cancel')}
            </Button>
            <Button type="submit" loading={respond.isPending}>
              {t('actions.respond')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
