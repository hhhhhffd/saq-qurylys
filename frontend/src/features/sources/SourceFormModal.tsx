import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm, useWatch } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { z } from 'zod';
import { useCreateSourceAccount } from '@/api/hooks/ads';
import type { Platform, SourceAccountInput } from '@/api/types';
import { SelectInput } from '@/components/form/SelectInput';
import { TextInput } from '@/components/form/TextInput';
import { ObjectSelect } from '@/components/ObjectSelect';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { isHttpUrl } from '@/features/ads/url';
import { useEnumOptions } from '@/i18n/useEnum';
import { aggregatorSite, SOURCE_PLATFORMS } from './collectors';

export function SourceFormModal({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation('sources');
  const { t: tc } = useTranslation('common');
  const enumOptions = useEnumOptions();
  const create = useCreateSourceAccount();

  const schema = useMemo(
    () =>
      z
        .object({
          platform: z.custom<Platform>().nullable(),
          /** channel or account (telegram, instagram) or the label of a search (aggregator) */
          handle: z.string(),
          url: z.string(),
          object_id: z.number().nullable(),
        })
        .superRefine((values, context) => {
          const issue = (path: 'platform' | 'handle' | 'url', message: string) =>
            context.addIssue({ code: 'custom', path: [path], message });
          if (!values.platform) return issue('platform', tc('required'));
          if (values.platform !== 'aggregator') {
            if (!values.handle.trim()) issue('handle', tc('required'));
            return;
          }
          const url = values.url.trim();
          if (!url) issue('url', tc('required'));
          else if (!isHttpUrl(url) || aggregatorSite(url) === null) issue('url', t('form.urlInvalid'));
        }),
    [t, tc],
  );
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { platform: null as Platform | null, handle: '', url: '', object_id: null as number | null },
  });
  const platform = useWatch({ control, name: 'platform' });

  const submit = handleSubmit((values) => {
    if (values.platform === null) return;
    // A search of an aggregator finds the listings of any seller: it is not bound to an object.
    const input: SourceAccountInput = {
      platform: values.platform,
      object_id: values.platform === 'aggregator' ? null : values.object_id,
    };
    const handle = values.handle.trim();
    if (values.platform === 'aggregator') {
      input.url = values.url.trim();
      if (handle) input.handle = handle;
    } else if (isHttpUrl(handle)) {
      // A pasted address: the server takes the name from it.
      input.url = handle;
    } else {
      input.handle = handle.replace(/^@/, '');
    }
    create.mutate(input, { onSuccess: onClose });
  });

  const handleLabel =
    platform === 'aggregator'
      ? { label: t('form.label'), description: t('form.labelHint'), placeholder: t('form.labelPlaceholder') }
      : platform === 'instagram'
        ? {
            label: t('form.instagramHandle'),
            description: t('form.instagramHandleHint'),
            placeholder: t('form.instagramHandlePlaceholder'),
          }
        : {
            label: t('form.telegramHandle'),
            description: t('form.telegramHandleHint'),
            placeholder: t('form.telegramHandlePlaceholder'),
          };

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{t('form.title')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="flex flex-col gap-3">
          <Controller
            control={control}
            name="platform"
            render={({ field }) => (
              <SelectInput
                label={t('form.platform')}
                data={enumOptions('platform', SOURCE_PLATFORMS)}
                required
                value={field.value}
                onChange={field.onChange}
                error={errors.platform?.message}
              />
            )}
          />
          {platform !== null && (
            <TextInput
              {...handleLabel}
              autoComplete="off"
              required={platform !== 'aggregator'}
              error={errors.handle?.message}
              {...register('handle')}
            />
          )}
          {platform === 'aggregator' && (
            <TextInput
              label={t('form.url')}
              description={t('form.urlHint')}
              placeholder={t('form.urlPlaceholder')}
              inputMode="url"
              autoComplete="off"
              required
              error={errors.url?.message}
              {...register('url')}
            />
          )}
          {platform !== 'aggregator' && (
            <>
              <Controller
                control={control}
                name="object_id"
                render={({ field }) => (
                  <ObjectSelect label={t('form.object')} value={field.value} onChange={field.onChange} />
                )}
              />
              <p className="m-0 text-sm text-text-2">{t('form.objectNote')}</p>
            </>
          )}
          <DialogFooter>
            <Button type="submit" className="max-sm:min-h-11" loading={create.isPending}>
              {tc('save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
