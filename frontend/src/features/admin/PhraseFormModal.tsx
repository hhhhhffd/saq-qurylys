import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useCreatePhrase, useUpdatePhrase } from '@/api/hooks/reference';
import type { Phrase, PhraseCategory, PhraseInput } from '@/api/types';
import { NumberInput } from '@/components/form/NumberInput';
import { SelectInput } from '@/components/form/SelectInput';
import { SwitchInput } from '@/components/form/SwitchInput';
import { TagsInput } from '@/components/form/TagsInput';
import { TextInput } from '@/components/form/TextInput';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useEnumOptions } from '@/i18n/useEnum';
import { PHRASE_CATEGORIES } from './phraseCategories';

interface FormValues {
  text: string;
  variants: string[];
  category: PhraseCategory | null;
  weight: number | string;
  is_active: boolean;
}

interface Props {
  /** edit mode when provided, create mode otherwise */
  phrase?: Phrase;
  onClose: () => void;
}

export function PhraseFormModal({ phrase, onClose }: Props) {
  const { t } = useTranslation('admin');
  const { t: tc } = useTranslation('common');
  const enumOptions = useEnumOptions();
  const create = useCreatePhrase();
  const update = useUpdatePhrase();

  const schema = useMemo(
    () =>
      z.object({
        text: z.string().trim().min(1, tc('required')),
        variants: z.array(z.string()),
        category: z.enum(PHRASE_CATEGORIES).nullable().refine((value) => value !== null, tc('required')),
        weight: z.union([z.number(), z.string()]).refine((value) => typeof value === 'number' && Number.isInteger(value), tc('required')),
        is_active: z.boolean(),
      }),
    [tc],
  );

  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      text: phrase?.text ?? '',
      variants: phrase?.variants ?? [],
      category: phrase?.category ?? null,
      weight: phrase?.weight ?? '',
      is_active: phrase?.is_active ?? true,
    },
  });

  const submit = handleSubmit((values) => {
    const { category, weight } = values;
    if (category === null || typeof weight !== 'number') return;
    const payload: PhraseInput = {
      text: values.text.trim(),
      variants: values.variants,
      category,
      weight,
      is_active: values.is_active,
    };
    if (phrase) update.mutate({ id: phrase.id, data: payload }, { onSuccess: onClose });
    else create.mutate(payload, { onSuccess: onClose });
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-lg" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{phrase ? t('phrases.form.editTitle') : t('phrases.form.createTitle')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="grid gap-3">
          <TextInput label={t('phrases.form.text')} required autoComplete="off" error={errors.text?.message} {...register('text')} />
          <Controller
            control={control}
            name="variants"
            render={({ field }) => (
              <TagsInput
                label={t('phrases.form.variants')}
                description={t('phrases.form.variantsHint')}
                placeholder={t('phrases.form.variantsPlaceholder')}
                splitChars={[',', ';']}
                value={field.value}
                onChange={field.onChange}
              />
            )}
          />
          <Controller
            control={control}
            name="category"
            render={({ field, fieldState }) => (
              <SelectInput
                label={t('phrases.form.category')}
                data={enumOptions('phrase_category', PHRASE_CATEGORIES)}
                required
                value={field.value}
                onChange={field.onChange}
                error={fieldState.error?.message}
              />
            )}
          />
          <Controller
            control={control}
            name="weight"
            render={({ field, fieldState }) => (
              <NumberInput
                label={t('phrases.form.weight')}
                description={t('phrases.form.weightHint')}
                allowDecimal={false}
                required
                value={field.value}
                onChange={field.onChange}
                error={fieldState.error?.message}
              />
            )}
          />
          <Controller
            control={control}
            name="is_active"
            render={({ field }) => (
              <SwitchInput label={t('phrases.form.isActive')} checked={field.value} onCheckedChange={field.onChange} />
            )}
          />
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={onClose}>
              {tc('cancel')}
            </Button>
            <Button type="submit" loading={create.isPending || update.isPending}>
              {tc('save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
