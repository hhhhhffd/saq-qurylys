import { useState } from 'react';
import { IconFileTypePdf } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { downloadFile } from '@/api/client';
import { useCloseSignal } from '@/api/hooks/signals';
import { errorMessage } from '@/api/queryClient';
import type { SignalDetail, SignalRecipient } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { MovingBorder } from '@/components/fx/MovingBorder';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { confirmAction } from '@/lib/confirm';
import { toast } from '@/lib/toast';
import { ConfirmSendModal } from './ConfirmSendModal';
import { ResponseModal } from './ResponseModal';
import { ReturnModal } from './ReturnModal';
import { useApplySignal } from './useApplySignal';

type Dialog = 'send' | 'return' | 'respond';

/** Downloads a file with the busy state and the error toast (`downloadFile` is not a mutation, so the global toast does not cover it). */
function DownloadButton({ path, filename, label }: { path: string; filename: string; label: string }) {
  const { t: tc } = useTranslation();
  const [loading, setLoading] = useState(false);

  const download = async () => {
    setLoading(true);
    try {
      await downloadFile(path, filename);
    } catch (error) {
      toast.error(errorMessage(error), { title: tc('error') });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button
      variant="secondary"
      loading={loading}
      // The label of the sent copy is long: it wraps on a narrow screen instead of widening the page.
      className="h-auto min-h-7 max-w-full py-1 whitespace-normal"
      onClick={() => void download()}
    >
      <IconFileTypePdf />
      {label}
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
  // A card addressed to the MIO itself is answered by a mio officer (OPEN_QUESTIONS #15).
  const canRespond =
    detail.status === 'sent' &&
    ((isRecipient && user?.role === detail.recipient) || (user?.role === 'mio_officer' && detail.recipient === 'mio'));
  const canClose = canManageSignals && detail.status === 'responded';

  let sendBlocker: string | null = null;
  if (!recipient) sendBlocker = t('actions.needRecipient');
  else if (dirty) sendBlocker = t('actions.saveFirst');

  const close = () => setDialog(null);

  return (
    <>
      <DownloadButton path={`/signals/${detail.id}/pdf`} filename={`${detail.number}.pdf`} label={t('detail.pdf')} />
      {detail.sent_pdf_evidence_id !== null && (
        <DownloadButton
          path={`/evidence/${detail.sent_pdf_evidence_id}/content`}
          filename={`${detail.number}-sent.pdf`}
          label={t('detail.sentPdf')}
        />
      )}
      {canReview && (
        <>
          <Button variant="secondary" onClick={() => setDialog('return')}>
            {t('actions.return')}
          </Button>
          {sendBlocker === null ? (
            <MovingBorder>
              <Button onClick={() => setDialog('send')}>{t('actions.confirmSend')}</Button>
            </MovingBorder>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button disabled>{t('actions.confirmSend')}</Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>{sendBlocker}</TooltipContent>
            </Tooltip>
          )}
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
