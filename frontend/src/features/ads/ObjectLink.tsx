import { useState } from 'react';
import { Link } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useUpdateAd } from '@/api/hooks/ads';
import { useSettings } from '@/api/hooks/reference';
import type { AdDetail, AdRow } from '@/api/types';
import { Chip } from '@/components/Chip';
import { ObjectSelect } from '@/components/ObjectSelect';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useEnum } from '@/i18n/useEnum';
import { DEFAULT_LINK_THRESHOLD } from './constants';

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
  const [feedback, setFeedback] = useState<'saved' | 'confirmed' | null>(null);

  const target =
    linked ?? (ad.object_id !== null ? { id: ad.object_id, code: null, name: ad.object_name ?? '' } : null);
  const targetId = target?.id ?? null;

  const rawThreshold = settings?.link_confidence_threshold;
  const threshold = typeof rawThreshold === 'number' ? rawThreshold : DEFAULT_LINK_THRESHOLD;
  const confidence = ad.link_confidence;
  const lowConfidence = target !== null && confidence !== null && confidence < threshold;
  const needsConfirmation = target !== null && ad.status === 'verification';

  const toggle = (next: boolean) => {
    if (next) {
      setDraft(targetId);
      setFeedback(null);
    }
    setOpened(next);
  };
  const save = () =>
    updateAd.mutate({ id: ad.id, data: { object_id: draft } }, { onSuccess: () => { setOpened(false); setFeedback('saved'); } });
  const confirmLink = () =>
    updateAd.mutate({ id: ad.id, data: { status: 'captured' } }, { onSuccess: () => setFeedback('confirmed') });

  return (
    <div className="flex min-w-0 flex-col gap-1 text-sm">
      <span className="text-xs font-medium text-text-3">{t('link.label')}</span>
      <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1.5">
        {target ? (
          <span className="font-semibold [overflow-wrap:anywhere]">
            {[target.code, target.name].filter(Boolean).join(' · ')}
          </span>
        ) : (
          <span className="text-text-3">{t('link.none')}</span>
        )}
        {editable && (
          <Popover open={opened} onOpenChange={toggle}>
            <PopoverTrigger asChild>
              <Button className="max-sm:min-h-11" size="xs" variant="secondary">
                {target ? t('link.change') : t('link.attach')}
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[min(20rem,calc(100vw-2rem))] gap-3 p-3">
              <ObjectSelect
                label={t('link.object')}
                placeholder={t('link.objectPlaceholder')}
                value={draft}
                onChange={setDraft}
              />
              <div className="flex justify-end gap-2">
                <Button variant="secondary" size="sm" onClick={() => setOpened(false)}>
                  {t('cancel', { ns: 'common' })}
                </Button>
                <Button className="max-sm:min-h-11" size="sm" disabled={draft === targetId} loading={updateAd.isPending} onClick={save}>
                  {t('save', { ns: 'common' })}
                </Button>
              </div>
            </PopoverContent>
          </Popover>
        )}
        {editable && needsConfirmation && (
          <Button
            size="xs"
            className="max-sm:min-h-11"
            variant="secondary"
            loading={updateAd.isPending && updateAd.variables.data.status === 'captured'}
            onClick={confirmLink}
          >
            {t('link.confirm')}
          </Button>
        )}
        {target && (
          <Button className="max-sm:min-h-11" size="sm" asChild>
            <Link to={`/objects/${target.id}`}>{t('link.checkObject')}</Link>
          </Button>
        )}
      </div>
      {!target && <p className="m-0 text-sm text-text-2">{t(editable ? 'link.unlinkedHint' : 'link.unlinkedReadOnlyHint')}</p>}
      {feedback && (
        <p className="m-0 text-sm text-zone-green-ink" role="status">
          {t(feedback === 'saved' ? 'link.savedFeedback' : 'link.confirmedFeedback')}
        </p>
      )}
      {lowConfidence && (
        <p className="m-0 text-sm text-zone-yellow-ink">{t('link.lowConfidence', { threshold: Math.round(threshold * 100) })}</p>
      )}
      {!lowConfidence && needsConfirmation && <p className="m-0 text-sm text-zone-yellow-ink">{t('link.needsConfirmation')}</p>}
      {target && (confidence !== null || ad.link_method) && (
        <details className="text-xs text-text-3">
          <summary className="inline-flex cursor-pointer items-center gap-1 hover:text-text-2 max-sm:min-h-11">
            {t('link.matchDetails')}
          </summary>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
            {confidence !== null && <span className="tabular-nums">{t('link.confidence', { value: Math.round(confidence * 100) })}</span>}
            {ad.link_method && <Chip>{e('link_method', ad.link_method)}</Chip>}
          </div>
        </details>
      )}
    </div>
  );
}
