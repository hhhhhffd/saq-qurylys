import { Button, Group, Modal, Stack, Textarea } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { useReturnSignal } from '@/api/hooks/signals';
import type { SignalDetail } from '@/api/types';
import { MIN_RETURN_COMMENT } from './constants';
import { useApplySignal } from './useApplySignal';

interface Props {
  opened: boolean;
  onClose: () => void;
  detail: SignalDetail;
}

export function ReturnModal({ opened, onClose, detail }: Props) {
  const { t } = useTranslation('signals');
  const { t: tc } = useTranslation();
  const returnSignal = useReturnSignal();
  const apply = useApplySignal();
  const form = useForm({
    initialValues: { comment: '' },
    validate: {
      comment: (value) => (value.trim().length < MIN_RETURN_COMMENT ? t('return.tooShort', { count: MIN_RETURN_COMMENT }) : null),
    },
  });

  const close = () => {
    form.reset();
    onClose();
  };

  const submit = form.onSubmit((values) =>
    returnSignal.mutate(
      { id: detail.id, comment: values.comment.trim() },
      {
        onSuccess: (next) => {
          apply(next);
          close();
        },
      },
    ),
  );

  return (
    <Modal opened={opened} onClose={close} title={t('actions.return')}>
      <form onSubmit={submit}>
        <Stack gap="md">
          <Textarea
            label={t('return.label')}
            description={t('return.description')}
            placeholder={t('return.placeholder')}
            withAsterisk
            autosize
            minRows={4}
            maxRows={10}
            data-autofocus
            {...form.getInputProps('comment')}
          />
          <Group justify="flex-end" gap="sm">
            <Button variant="default" onClick={close} disabled={returnSignal.isPending}>
              {tc('cancel')}
            </Button>
            <Button type="submit" loading={returnSignal.isPending}>
              {t('actions.return')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
