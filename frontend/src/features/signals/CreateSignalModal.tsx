import { useState } from 'react';
import { Button, Group, Modal, Stack, Text } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { useCreateSignal } from '@/api/hooks/signals';
import { ObjectSelect } from '@/components/ObjectSelect';
import { useApplySignal } from './useApplySignal';

interface Props {
  opened: boolean;
  onClose: () => void;
}

export function CreateSignalModal({ opened, onClose }: Props) {
  const { t } = useTranslation('signals');
  const { t: tc } = useTranslation();
  const navigate = useNavigate();
  const create = useCreateSignal();
  const apply = useApplySignal();
  const [objectId, setObjectId] = useState<number | null>(null);

  const close = () => {
    setObjectId(null);
    onClose();
  };

  const submit = () => {
    if (objectId === null) return;
    create.mutate(objectId, {
      onSuccess: (card) => {
        apply(card);
        close();
        void navigate(`/signals/${card.id}`);
      },
    });
  };

  return (
    <Modal opened={opened} onClose={close} title={t('create.title')}>
      <Stack gap="md">
        <Text size="sm" c="dimmed">
          {t('create.hint')}
        </Text>
        <ObjectSelect
          label={t('create.object')}
          placeholder={t('create.objectPlaceholder')}
          value={objectId}
          onChange={setObjectId}
          data-autofocus
        />
        <Group justify="flex-end" gap="sm">
          <Button variant="default" onClick={close}>
            {tc('cancel')}
          </Button>
          <Button onClick={submit} disabled={objectId === null} loading={create.isPending}>
            {t('create.submit')}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
