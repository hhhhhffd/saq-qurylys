import { useState } from 'react';
import { Button, Group, Popover } from '@mantine/core';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useUpdateAd } from '@/api/hooks/ads';
import { useSettings } from '@/api/hooks/reference';
import type { AdDetail, AdRow } from '@/api/types';
import { Chip } from '@/components/Chip';
import { ObjectSelect } from '@/components/ObjectSelect';
import { useEnum } from '@/i18n/useEnum';
import { DEFAULT_LINK_THRESHOLD } from './constants';
import classes from './AdCard.module.css';

interface Props {
  ad: AdRow;
  /** from the ad detail; until it loads the row's id and name are shown */
  linked: AdDetail['linked_object'];
  editable: boolean;
}

export function ObjectLink({ ad, linked, editable }: Props) {
  const { t } = useTranslation('ads');
  const e = useEnum();
  const { data: settings } = useSettings();
  const updateAd = useUpdateAd();
  const [opened, setOpened] = useState(false);
  const [draft, setDraft] = useState<number | null>(null);

  const target =
    linked ?? (ad.object_id !== null ? { id: ad.object_id, code: null, name: ad.object_name ?? '' } : null);
  const targetId = target?.id ?? null;

  const rawThreshold = settings?.link_confidence_threshold;
  const threshold = typeof rawThreshold === 'number' ? rawThreshold : DEFAULT_LINK_THRESHOLD;
  const confidence = ad.link_confidence;
  const lowConfidence = target !== null && confidence !== null && confidence < threshold;
  const needsConfirmation = target !== null && ad.status === 'verification';

  const toggle = () => {
    if (!opened) setDraft(targetId);
    setOpened(!opened);
  };
  const save = () => updateAd.mutate({ id: ad.id, data: { object_id: draft } }, { onSuccess: () => setOpened(false) });
  const confirmLink = () => updateAd.mutate({ id: ad.id, data: { status: 'captured' } });

  return (
    <div className={classes.fact}>
      <span className={classes.label}>{t('link.label')}</span>
      <div className={classes.chips}>
        {target ? (
          <Link to={`/objects/${target.id}`} className={classes.objectLink}>
            {[target.code, target.name].filter(Boolean).join(' · ')}
          </Link>
        ) : (
          <span className="faint">{t('link.none')}</span>
        )}
        {target && confidence !== null && (
          <span className="tnum faint">{t('link.confidence', { value: Math.round(confidence * 100) })}</span>
        )}
        {target && ad.link_method && <Chip>{e('link_method', ad.link_method)}</Chip>}
        {editable && (
          <Popover opened={opened} onChange={setOpened} position="bottom-start" width={320} trapFocus>
            <Popover.Target>
              <Button size="compact-xs" variant="default" onClick={toggle}>
                {target ? t('link.change') : t('link.attach')}
              </Button>
            </Popover.Target>
            <Popover.Dropdown>
              <ObjectSelect
                label={t('link.object')}
                placeholder={t('link.objectPlaceholder')}
                value={draft}
                onChange={setDraft}
                comboboxProps={{ withinPortal: false, shadow: 'md' }}
              />
              <Group justify="flex-end" mt="sm" gap="xs">
                <Button variant="default" size="xs" onClick={() => setOpened(false)}>
                  {t('cancel', { ns: 'common' })}
                </Button>
                <Button size="xs" disabled={draft === targetId} loading={updateAd.isPending} onClick={save}>
                  {t('save', { ns: 'common' })}
                </Button>
              </Group>
            </Popover.Dropdown>
          </Popover>
        )}
        {editable && needsConfirmation && (
          <Button
            size="compact-xs"
            variant="default"
            loading={updateAd.isPending && updateAd.variables.data.status === 'captured'}
            onClick={confirmLink}
          >
            {t('link.confirm')}
          </Button>
        )}
      </div>
      {lowConfidence && (
        <p className={classes.warn}>{t('link.lowConfidence', { threshold: Math.round(threshold * 100) })}</p>
      )}
      {!lowConfidence && needsConfirmation && <p className={classes.warn}>{t('link.needsConfirmation')}</p>}
    </div>
  );
}
