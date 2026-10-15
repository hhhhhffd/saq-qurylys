import { useState } from 'react';
import { IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import type { ObjectDetail } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Chip } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { EvidenceThumbs } from '@/components/evidence/EvidenceImage';
import { Button } from '@/components/ui/button';
import { useFormat } from '@/i18n/useFormat';
import { cn } from '@/lib/utils';
import { InspectionFormModal } from '../forms/InspectionFormModal';
import { anchorId } from '@/components/risk/anchors';
import { anchorTargetClass } from './styles';

export function InspectionsSection({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('objects');
  const { date } = useFormat();
  const { canEditRegistry } = useAuth();
  const [adding, setAdding] = useState(false);

  const inspections = [...object.inspections].sort(
    (a, b) => b.inspected_at.localeCompare(a.inspected_at) || b.id - a.id,
  );

  return (
    <Panel
      title={t('card.inspections.title')}
      id="inspections"
      flush
      actions={
        canEditRegistry && (
          <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
            <IconPlus />
            {t('card.inspections.add')}
          </Button>
        )
      }
    >
      {inspections.length === 0 ? (
        <p className="px-4 pb-4 text-text-3">{t('card.inspections.empty')}</p>
      ) : (
        <ul>
          {inspections.map((item, index) => {
            const pct = Math.min(100, Math.max(0, item.readiness_pct));
            return (
              <li
                key={item.id}
                id={anchorId('inspection', item.id)}
                className={cn('border-t border-border px-4 py-3 first:border-t-0', anchorTargetClass)}
              >
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
                  <strong className="tabular-nums">{date(item.inspected_at)}</strong>
                  {index === 0 && <Chip>{t('card.inspections.latest')}</Chip>}
                  <span className="ml-auto text-text-2">
                    {t('card.inspections.readiness')} <strong className="tabular-nums">{item.readiness_pct}%</strong>
                  </span>
                </div>
                <div
                  className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-sunken"
                  role="progressbar"
                  aria-label={t('card.inspections.readiness')}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={pct}
                >
                  <div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} />
                </div>
                {item.note && <p className="mt-2 text-text-2 [overflow-wrap:anywhere]">{item.note}</p>}
                {item.evidence.length > 0 && (
                  <div className="mt-2.5">
                    <EvidenceThumbs evidence={item.evidence} size={64} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {canEditRegistry && (
        <InspectionFormModal opened={adding} onClose={() => setAdding(false)} objectId={object.id} />
      )}
    </Panel>
  );
}
