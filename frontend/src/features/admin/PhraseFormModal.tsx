import { Button, Group, Modal, NumberInput, Select, Stack, Switch, TagsInput, TextInput } from '@mantine/core';
import { useForm } from '@mantine/form';
import { useTranslation } from 'react-i18next';
import { useCreatePhrase, useUpdatePhrase } from '@/api/hooks/reference';
import type { Phrase, PhraseCategory, PhraseInput } from '@/api/types';
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

  const form = useForm<FormValues>({
    initialValues: {
      text: phrase?.text ?? '',
      variants: phrase?.variants ?? [],
      category: phrase?.category ?? null,
      weight: phrase?.weight ?? '',
      is_active: phrase?.is_active ?? true,
    },
    validate: {
      text: (value) => (value.trim() ? null : tc('required')),
      category: (value) => (value ? null : tc('required')),
      weight: (value) => (typeof value === 'number' && Number.isInteger(value) ? null : tc('required')),
    },
  });

  const submit = form.onSubmit((values) => {
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
    <Modal opened onClose={onClose} title={phrase ? t('phrases.form.editTitle') : t('phrases.form.createTitle')}>
      <form onSubmit={submit} noValidate>
        <Stack gap="sm">
          <TextInput label={t('phrases.form.text')} withAsterisk autoComplete="off" {...form.getInputProps('text')} />
          <TagsInput
            label={t('phrases.form.variants')}
            description={t('phrases.form.variantsHint')}
            placeholder={t('phrases.form.variantsPlaceholder')}
            splitChars={[',', ';']}
            {...form.getInputProps('variants')}
          />
          <Select
            label={t('phrases.form.category')}
            data={enumOptions('phrase_category', PHRASE_CATEGORIES)}
            allowDeselect={false}
            withAsterisk
            {...form.getInputProps('category')}
          />
          <NumberInput
            label={t('phrases.form.weight')}
            description={t('phrases.form.weightHint')}
            allowDecimal={false}
            withAsterisk
            {...form.getInputProps('weight')}
          />
          <Switch label={t('phrases.form.isActive')} {...form.getInputProps('is_active', { type: 'checkbox' })} />
          <Group justify="flex-end" mt="xs">
            <Button variant="default" onClick={onClose}>
              {tc('cancel')}
            </Button>
            <Button type="submit" loading={create.isPending || update.isPending}>
              {tc('save')}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
