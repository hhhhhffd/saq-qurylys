import { IconSend } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useConfirmAndSend } from '@/api/hooks/signals';
import type { SignalDetail, SignalRecipient } from '@/api/types';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useEnum } from '@/i18n/useEnum';
import { Callout } from './Callout';
import { useApplySignal } from './useApplySignal';

interface Props {
  opened: boolean;
  onClose: () => void;
  detail: SignalDetail;
  recipient: SignalRecipient;
}

/** The only way data leaves the system, so the dialog spells out where it goes and that it cannot be undone. */
export function ConfirmSendModal({ opened, onClose, detail, recipient }: Props) {
  const { t } = useTranslation('signals');
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
    <Dialog open={opened} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('actions.confirmSend')}</DialogTitle>
          <DialogDescription>{t('confirmSend.description')}</DialogDescription>
        </DialogHeader>
        <Callout tone="warning" icon={<IconSend size={18} />} title={t('confirmSend.headline', { number: detail.number })}>
          <strong>{t('confirmSend.recipient', { recipient: e('recipient', recipient) })}</strong>
        </Callout>
        <ul className="flex list-disc flex-col gap-1.5 pl-5 text-sm text-text-2">
          <li>{t('confirmSend.onlyOutbound')}</li>
          <li>{t('confirmSend.locked')}</li>
          <li>{t('confirmSend.deadline', { days: t('reviewDays', { count: detail.review_days }) })}</li>
          <li>{t('confirmSend.archive')}</li>
          <li>{t('confirmSend.email')}</li>
        </ul>
        <DialogFooter>
          <Button className="min-h-11" onClick={submit} loading={send.isPending}>
            {t('actions.confirmSend')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
