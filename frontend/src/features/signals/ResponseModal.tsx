import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useRespondSignal } from '@/api/hooks/signals';
import type { SignalDetail } from '@/api/types';
import { TextArea } from '@/components/form/TextArea';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { MIN_RESPONSE_TEXT } from './constants';
import { useApplySignal } from './useApplySignal';

interface Props {
  opened: boolean;
  onClose: () => void;
  detail: SignalDetail;
}

export function ResponseModal({ opened, onClose, detail }: Props) {
  const { t } = useTranslation('signals');
  const respond = useRespondSignal();
  const apply = useApplySignal();
  const schema = useMemo(
    () => z.object({ response: z.string().trim().min(MIN_RESPONSE_TEXT, t('respond.tooShort', { count: MIN_RESPONSE_TEXT })) }),
    [t],
  );
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm({ resolver: zodResolver(schema), defaultValues: { response: '' } });

  const close = () => {
    reset();
    onClose();
  };

  const submit = handleSubmit((values) =>
    respond.mutate(
      { id: detail.id, response_text: values.response },
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
          <DialogTitle>{t('actions.respond')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <TextArea
            label={t('respond.label')}
            description={t('respond.description', { number: detail.number })}
            placeholder={t('respond.placeholder')}
            required
            minRows={5}
            maxRows={12}
            error={errors.response?.message}
            {...register('response')}
          />
          <DialogFooter>
            <Button className="min-h-11" type="submit" loading={respond.isPending}>
              {t('actions.respond')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
