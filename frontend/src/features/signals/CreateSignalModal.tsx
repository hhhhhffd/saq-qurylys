import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { useCreateSignal } from '@/api/hooks/signals';
import { ObjectSelect } from '@/components/ObjectSelect';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useApplySignal } from './useApplySignal';

interface Props {
  opened: boolean;
  onClose: () => void;
}

export function CreateSignalModal({ opened, onClose }: Props) {
  const { t } = useTranslation('signals');
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
    <Dialog open={opened} onOpenChange={(open) => !open && close()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t('create.title')}</DialogTitle>
          <DialogDescription>{t('create.hint')}</DialogDescription>
        </DialogHeader>
        <ObjectSelect label={t('create.object')} placeholder={t('create.objectPlaceholder')} value={objectId} onChange={setObjectId} />
        <DialogFooter>
          <Button onClick={submit} disabled={objectId === null} loading={create.isPending}>
            {t('create.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
