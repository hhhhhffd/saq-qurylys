import { useState } from 'react';
import { IconPencil } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import type { ObjectDetail } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { KeyValue } from '@/components/KeyValue';
import { Panel } from '@/components/Panel';
import { Button } from '@/components/ui/button';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { DeveloperFormModal } from '../forms/DeveloperFormModal';
import { subTitleClass } from './styles';

function joinList(items: string[]): string | null {
  return items.length > 0 ? items.join(', ') : null;
}

export function PassportSection({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const { date } = useFormat();
  const { canEditRegistry } = useAuth();
  const [editingDeveloper, setEditingDeveloper] = useState(false);
  const { developer } = object;
  const coordinates =
    object.lat !== null && object.lon !== null ? `${object.lat.toFixed(6)}, ${object.lon.toFixed(6)}` : null;

  return (
    <Panel title={t('card.passport.title')} id="passport">
      <KeyValue
        items={[
          { label: t('card.passport.name'), value: object.name, wide: true },
          { label: t('card.passport.aliases'), value: joinList(object.aliases), wide: true },
          { label: t('card.passport.address'), value: object.address, wide: true },
          { label: t('card.passport.cadastralNumber'), value: object.cadastral_number },
          { label: t('card.passport.landPurpose'), value: object.land_purpose },
          { label: t('card.passport.district'), value: object.district_name },
          {
            label: t('card.passport.coordinates'),
            value: coordinates && <span className="tabular-nums">{coordinates}</span>,
          },
          { label: t('card.passport.plannedCompletion'), value: date(object.planned_completion) },
          { label: t('card.passport.forecastCompletion'), value: date(object.forecast_completion) },
          { label: t('card.passport.constructionStatus'), value: e('construction_status', object.construction_status) },
          { label: t('card.passport.stalledSince'), value: date(object.stalled_since) },
          { label: t('card.passport.priorViolations'), value: object.prior_violations, wide: true },
        ]}
      />

      <section className="mt-4 border-t border-border pt-3" aria-labelledby="passport-developer">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
          <h4 id="passport-developer" className={subTitleClass}>
            {t('card.passport.developer.title')}
          </h4>
          {canEditRegistry && developer && (
            <Button variant="ghost" size="sm" onClick={() => setEditingDeveloper(true)}>
              <IconPencil />
              {t('card.passport.developer.edit')}
            </Button>
          )}
        </div>
        {developer ? (
          <KeyValue
            items={[
              { label: t('card.passport.developer.bin'), value: <span className="tabular-nums">{developer.bin}</span> },
              { label: t('card.passport.developer.name'), value: developer.name },
              { label: t('card.passport.developer.director'), value: developer.director },
              { label: t('card.passport.developer.authorizedCompany'), value: developer.authorized_company },
              { label: t('card.passport.developer.founders'), value: joinList(developer.founders), wide: true },
              { label: t('card.passport.developer.phones'), value: joinList(developer.phones), wide: true },
            ]}
          />
        ) : (
          <p className="text-text-3">{t('card.passport.developer.none')}</p>
        )}
      </section>

      {canEditRegistry && developer && (
        <DeveloperFormModal opened={editingDeveloper} onClose={() => setEditingDeveloper(false)} developer={developer} />
      )}
    </Panel>
  );
}
