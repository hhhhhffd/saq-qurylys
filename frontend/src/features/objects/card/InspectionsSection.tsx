import { useState } from 'react';
import { Button } from '@mantine/core';
import { IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import type { ObjectDetail } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Chip } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { EvidenceThumbs } from '@/components/evidence/EvidenceImage';
import { useFormat } from '@/i18n/useFormat';
import { InspectionFormModal } from '../forms/InspectionFormModal';
import { anchorId } from './anchors';
import classes from './Section.module.css';
import ownClasses from './InspectionsSection.module.css';

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
          <Button variant="default" size="xs" leftSection={<IconPlus size={14} />} onClick={() => setAdding(true)}>
            {t('card.inspections.add')}
          </Button>
        )
      }
    >
      {inspections.length === 0 ? (
        <p className={`${classes.muted} ${classes.pad}`}>{t('card.inspections.empty')}</p>
      ) : (
        <ul className={classes.list}>
          {inspections.map((item, index) => {
            const pct = Math.min(100, Math.max(0, item.readiness_pct));
            return (
              <li key={item.id} id={anchorId('inspection', item.id)} className={`${classes.item} ${classes.target}`}>
                <div className={classes.itemHead}>
                  <strong className="tnum">{date(item.inspected_at)}</strong>
                  {index === 0 && <Chip>{t('card.inspections.latest')}</Chip>}
                  <span className={ownClasses.readiness}>
                    {t('card.inspections.readiness')} <strong className="tnum">{item.readiness_pct}%</strong>
                  </span>
                </div>
                <div
                  className={ownClasses.bar}
                  role="progressbar"
                  aria-label={t('card.inspections.readiness')}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={pct}
                >
                  <div className={ownClasses.fill} style={{ width: `${pct}%` }} />
                </div>
                {item.note && <p className={classes.text}>{item.note}</p>}
                {item.evidence.length > 0 && (
                  <div className={classes.thumbs}>
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
