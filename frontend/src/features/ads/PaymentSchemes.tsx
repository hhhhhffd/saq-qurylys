import { useState } from 'react';
import { ActionIcon, Button, Group, MultiSelect, Popover } from '@mantine/core';
import { IconPencil } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useUpdateAd } from '@/api/hooks/ads';
import type { AdRow, PaymentScheme } from '@/api/types';
import { Chip } from '@/components/Chip';
import { useEnum, useEnumOptions } from '@/i18n/useEnum';
import { PAYMENT_SCHEMES, parsePaymentSchemes } from './constants';
import classes from './AdCard.module.css';

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

  const toggle = () => {
    if (!opened) setDraft(ad.payment_schemes);
    setOpened(!opened);
  };
  const save = () =>
    updateAd.mutate({ id: ad.id, data: { payment_schemes: draft } }, { onSuccess: () => setOpened(false) });

  return (
    <div className={classes.fact}>
      <span className={classes.label}>{t('schemes.label')}</span>
      <div className={classes.chips}>
        {ad.payment_schemes.map((scheme) => (
          <Chip key={scheme}>{e('payment_scheme', scheme)}</Chip>
        ))}
        {ad.payment_schemes.length === 0 && <span className="faint">{t('schemes.none')}</span>}
        {editable && (
          <Popover opened={opened} onChange={setOpened} position="bottom-start" width={300} trapFocus>
            <Popover.Target>
              <ActionIcon size="sm" aria-label={t('schemes.edit')} onClick={toggle}>
                <IconPencil size={14} stroke={1.8} />
              </ActionIcon>
            </Popover.Target>
            <Popover.Dropdown>
              <MultiSelect
                label={t('schemes.label')}
                description={t('schemes.hint')}
                data={schemeOptions('payment_scheme', PAYMENT_SCHEMES)}
                value={draft}
                onChange={(values) => setDraft(parsePaymentSchemes(values))}
                comboboxProps={{ withinPortal: false, shadow: 'md' }}
              />
              <Group justify="flex-end" mt="sm" gap="xs">
                <Button variant="default" size="xs" onClick={() => setOpened(false)}>
                  {t('cancel', { ns: 'common' })}
                </Button>
                <Button size="xs" loading={updateAd.isPending} onClick={save}>
                  {t('save', { ns: 'common' })}
                </Button>
              </Group>
            </Popover.Dropdown>
          </Popover>
        )}
      </div>
    </div>
  );
}
