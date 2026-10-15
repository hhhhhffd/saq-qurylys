import { useState } from 'react';
import { IconPencil } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useUpdateAd } from '@/api/hooks/ads';
import type { AdRow, PaymentScheme } from '@/api/types';
import { Chip } from '@/components/Chip';
import { MultiSelect } from '@/components/form/MultiSelect';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useEnum, useEnumOptions } from '@/i18n/useEnum';
import { PAYMENT_SCHEMES, parsePaymentSchemes } from './constants';

interface Props {
  ad: AdRow;
  editable: boolean;
}

/** Confirmed payment schemes of an ad; staff can correct them directly. */
export function PaymentSchemes({ ad, editable }: Props) {
  const { t } = useTranslation('ads');
  const e = useEnum();
  const schemeOptions = useEnumOptions();
  const updateAd = useUpdateAd();
  const [opened, setOpened] = useState(false);
  const [draft, setDraft] = useState<PaymentScheme[]>([]);

  if (!editable && ad.payment_schemes.length === 0) return null;

  const toggle = (next: boolean) => {
    if (next) setDraft(ad.payment_schemes);
    setOpened(next);
  };
  const save = () =>
    updateAd.mutate({ id: ad.id, data: { payment_schemes: draft } }, { onSuccess: () => setOpened(false) });

  return (
    <div className="flex min-w-0 flex-col gap-1 text-sm">
      <span className="text-xs font-medium text-text-3">{t('schemes.label')}</span>
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1.5">
        {ad.payment_schemes.map((scheme) => (
          <Chip key={scheme}>{e('payment_scheme', scheme)}</Chip>
        ))}
        {ad.payment_schemes.length === 0 && <span className="text-text-3">{t('schemes.none')}</span>}
        {editable && (
          <Popover open={opened} onOpenChange={toggle}>
            <PopoverTrigger asChild>
              <Button size="icon-xs" variant="ghost" aria-label={t('schemes.edit')}>
                <IconPencil />
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-80 gap-3 p-3">
              <MultiSelect
                label={t('schemes.label')}
                description={t('schemes.hint')}
                data={schemeOptions('payment_scheme', PAYMENT_SCHEMES)}
                value={draft}
                onChange={(values) => setDraft(parsePaymentSchemes(values))}
              />
              <div className="flex justify-end gap-2">
                <Button variant="secondary" size="sm" onClick={() => setOpened(false)}>
                  {t('cancel', { ns: 'common' })}
                </Button>
                <Button size="sm" loading={updateAd.isPending} onClick={save}>
                  {t('save', { ns: 'common' })}
                </Button>
              </div>
            </PopoverContent>
          </Popover>
        )}
      </div>
    </div>
  );
}
