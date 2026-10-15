import { Button, Group, Modal, Stack } from '@mantine/core';
import { IconSend } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useConfirmAndSend } from '@/api/hooks/signals';
import type { SignalDetail, SignalRecipient } from '@/api/types';
import { useEnum } from '@/i18n/useEnum';
import { Callout } from './Callout';
import { useApplySignal } from './useApplySignal';
import classes from './ConfirmSendModal.module.css';

interface Props {
  opened: boolean;
  onClose: () => void;
  detail: SignalDetail;
  recipient: SignalRecipient;
}

/** The only way data leaves the system, so the dialog spells out where it goes and that it cannot be undone. */
export function ConfirmSendModal({ opened, onClose, detail, recipient }: Props) {
  const { t } = useTranslation('signals');
  const { t: tc } = useTranslation();
  const e = useEnum();
  const send = useConfirmAndSend();
  const apply = useApplySignal();

  const submit = () =>
    send.mutate(
      { id: detail.id, recipient },
      {
        onSuccess: (next) => {
          apply(next);
          onClose();
        },
      },
    );

  return (
    <Modal opened={opened} onClose={onClose} title={t('actions.confirmSend')} size="lg">
      <Stack gap="md">
        <Callout tone="warning" icon={<IconSend size={18} />} title={t('confirmSend.headline', { number: detail.number })}>
          <strong>{t('confirmSend.recipient', { recipient: e('recipient', recipient) })}</strong>
        </Callout>
        <ul className={classes.list}>
          <li>{t('confirmSend.onlyOutbound')}</li>
          <li>{t('confirmSend.locked')}</li>
          <li>{t('confirmSend.deadline', { days: t('reviewDays', { count: detail.review_days }) })}</li>
        </ul>
        <Group justify="flex-end" gap="sm">
          <Button variant="default" onClick={onClose} disabled={send.isPending}>
            {tc('cancel')}
          </Button>
          <Button onClick={submit} loading={send.isPending}>
            {t('actions.confirmSend')}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
