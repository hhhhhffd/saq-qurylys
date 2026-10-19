import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useReturnSignal } from '@/api/hooks/signals';
import type { SignalDetail } from '@/api/types';
import { TextArea } from '@/components/form/TextArea';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { MIN_RETURN_COMMENT } from './constants';
import { useApplySignal } from './useApplySignal';

interface Props {
  opened: boolean;
  onClose: () => void;
  detail: SignalDetail;
}

export function ReturnModal({ opened, onClose, detail }: Props) {
  const { t } = useTranslation('signals');
  const returnSignal = useReturnSignal();
  const apply = useApplySignal();
  const schema = useMemo(
    () => z.object({ comment: z.string().trim().min(MIN_RETURN_COMMENT, t('return.tooShort', { count: MIN_RETURN_COMMENT })) }),
    [t],
  );
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm({ resolver: zodResolver(schema), defaultValues: { comment: '' } });

  const close = () => {
    reset();
    onClose();
  };

  const submit = handleSubmit((values) =>
    returnSignal.mutate(
      { id: detail.id, comment: values.comment },
      {
        onSuccess: (next) => {
          apply(next);
          close();
        },
      },
    ),
  );

  return (
    <Dialog open={opened} onOpenChange={(open) => !open && close()}>
      <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{t('actions.return')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <TextArea
            label={t('return.label')}
            description={t('return.description')}
            placeholder={t('return.placeholder')}
            required
            minRows={4}
            maxRows={10}
            error={errors.comment?.message}
            {...register('comment')}
          />
          <DialogFooter>
            <Button className="min-h-11" type="submit" loading={returnSignal.isPending}>
              {t('actions.return')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
