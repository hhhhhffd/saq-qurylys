import { useState } from 'react';
import { Button, Tooltip } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconFileTypePdf } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { downloadFile } from '@/api/client';
import { useCloseSignal } from '@/api/hooks/signals';
import { errorMessage } from '@/api/queryClient';
import type { SignalDetail, SignalRecipient } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { confirmAction } from '@/lib/confirm';
import { ConfirmSendModal } from './ConfirmSendModal';
import { ResponseModal } from './ResponseModal';
import { ReturnModal } from './ReturnModal';
import { useApplySignal } from './useApplySignal';

type Dialog = 'send' | 'return' | 'respond';

function PdfButton({ detail }: { detail: SignalDetail }) {
  const { t } = useTranslation('signals');
  const { t: tc } = useTranslation();
  const [loading, setLoading] = useState(false);

  // downloadFile is not a mutation, so the global error toast does not cover it.
  const download = async () => {
    setLoading(true);
    try {
      await downloadFile(`/signals/${detail.id}/pdf`, `${detail.number}.pdf`);
    } catch (error) {
      notifications.show({ color: 'red', title: tc('error'), message: errorMessage(error) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button variant="default" leftSection={<IconFileTypePdf size={16} />} loading={loading} onClick={() => void download()}>
      {t('detail.pdf')}
    </Button>
  );
}

interface Props {
  detail: SignalDetail;
  /** recipient currently selected in the route section (draft or saved) */
  recipient: SignalRecipient | null;
  /** the card has edits that are not saved yet */
  dirty: boolean;
}

export function ActionsBar({ detail, recipient, dirty }: Props) {
  const { t } = useTranslation('signals');
  const { user, canManageSignals, isRecipient } = useAuth();
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const closeSignal = useCloseSignal();
  const apply = useApplySignal();

  const canReview = canManageSignals && detail.status === 'requires_confirmation';
  const canRespond = isRecipient && detail.status === 'sent' && user?.role === detail.recipient;
  const canClose = canManageSignals && detail.status === 'responded';

  let sendBlocker: string | null = null;
  if (!recipient) sendBlocker = t('actions.needRecipient');
  else if (dirty) sendBlocker = t('actions.saveFirst');

  const close = () => setDialog(null);

  return (
    <>
      <PdfButton detail={detail} />
      {canReview && (
        <>
          <Button variant="default" onClick={() => setDialog('return')}>
            {t('actions.return')}
          </Button>
          <Tooltip label={sendBlocker} disabled={sendBlocker === null}>
            <span>
              <Button disabled={sendBlocker !== null} onClick={() => setDialog('send')}>
                {t('actions.confirmSend')}
              </Button>
            </span>
          </Tooltip>
        </>
      )}
      {canRespond && <Button onClick={() => setDialog('respond')}>{t('actions.respond')}</Button>}
      {canClose && (
        <Button
          loading={closeSignal.isPending}
          onClick={() =>
            confirmAction({
              title: t('actions.close'),
              message: t('close.message', { number: detail.number }),
              confirmLabel: t('actions.close'),
              onConfirm: () => closeSignal.mutate(detail.id, { onSuccess: apply }),
            })
          }
        >
          {t('actions.close')}
        </Button>
      )}
      {canReview && recipient && (
        <ConfirmSendModal opened={dialog === 'send'} onClose={close} detail={detail} recipient={recipient} />
      )}
      {canReview && <ReturnModal opened={dialog === 'return'} onClose={close} detail={detail} />}
      {canRespond && <ResponseModal opened={dialog === 'respond'} onClose={close} detail={detail} />}
    </>
  );
}
