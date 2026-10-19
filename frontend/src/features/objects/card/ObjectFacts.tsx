import { useTranslation } from 'react-i18next';
import type { ObjectDetail } from '@/api/types';
import { CopyButton } from '@/components/CopyButton';
import { KeyValue } from '@/components/KeyValue';
import { Panel } from '@/components/Panel';
import { Button } from '@/components/ui/button';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';

/** Key facts of the passport for the side column; the full passport is a tab of its own. */
export function ObjectFacts({ object, onShowAll }: { object: ObjectDetail; onShowAll: () => void }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const { date } = useFormat();
  const { developer } = object;
  const coordinates =
    object.lat !== null && object.lon !== null ? `${object.lat.toFixed(6)}, ${object.lon.toFixed(6)}` : null;

  return (
    <Panel
      title={t('card.facts.title')}
      id="facts"
      actions={
        <Button variant="ghost" size="sm" data-print="hide" onClick={onShowAll}>
          {t('card.facts.all')}
        </Button>
      }
    >
      <KeyValue
        columns={1}
        items={[
          { label: t('card.passport.constructionStatus'), value: e('construction_status', object.construction_status) },
          { label: t('card.passport.district'), value: object.district_name },
          { label: t('card.passport.address'), value: object.address },
          { label: t('card.passport.plannedCompletion'), value: date(object.planned_completion) },
          { label: t('card.passport.forecastCompletion'), value: date(object.forecast_completion) },
          {
            label: t('card.facts.developer'),
            value: developer && (
              <span>
                {developer.name}
                <span className="mt-0.5 flex items-center gap-1 text-xs text-text-3">
                  {t('card.passport.developer.bin')} <span className="tabular-nums">{developer.bin}</span>
                  <CopyButton value={developer.bin} label={t('copy.bin')} />
                </span>
              </span>
            ),
          },
          { label: t('card.passport.coordinates'), value: coordinates && <span className="tabular-nums">{coordinates}</span> },
        ]}
      />
    </Panel>
  );
}
