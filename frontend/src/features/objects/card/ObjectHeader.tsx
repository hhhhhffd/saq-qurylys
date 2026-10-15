import { useState } from 'react';
import { IconArrowLeft, IconFilePlus, IconPencil, IconRefresh, IconTopologyStar3 } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';
import { useRecalculateObject } from '@/api/hooks/objects';
import { useCreateSignal } from '@/api/hooks/signals';
import type { ObjectDetail } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Chip } from '@/components/Chip';
import { DemoBadge } from '@/components/DemoBadge';
import { Button } from '@/components/ui/button';
import { ZoneBadge } from '@/components/Zone';
import { ZoneDisclaimer } from '@/components/ZoneDisclaimer';
import { useFormat } from '@/i18n/useFormat';
import { useKeyStatusLabel } from '@/i18n/useEnum';
import { ObjectFormModal } from '../forms/ObjectFormModal';

export function ObjectHeader({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('objects');
  const { t: tGraph } = useTranslation('graph');
  const { dateTime } = useFormat();
  const keyStatusLabel = useKeyStatusLabel();
  const { canEditRegistry, canManageSignals } = useAuth();
  const navigate = useNavigate();
  const recalculate = useRecalculateObject();
  const createSignal = useCreateSignal();
  const [editing, setEditing] = useState(false);

  const handleCreateSignal = () =>
    createSignal.mutate(object.id, { onSuccess: (signal) => void navigate(`/signals/${signal.id}`) });

  return (
    <header className="mb-4 flex flex-col gap-3">
      <Link to="/objects" className="inline-flex items-center gap-1 self-start text-sm text-text-2 hover:text-text">
        <IconArrowLeft size={16} stroke={1.8} aria-hidden />
        {t('card.back')}
      </Link>

      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="mb-1 font-mono text-xs tracking-wide text-text-3">{object.code}</p>
          <h1 className="font-heading text-2xl font-bold [overflow-wrap:anywhere]">{object.name}</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button asChild variant="secondary">
            <Link to={`/graph?object_id=${object.id}`}>
              <IconTopologyStar3 />
              {tGraph('open')}
            </Link>
          </Button>
          {canEditRegistry && (
            <Button variant="secondary" loading={recalculate.isPending} onClick={() => recalculate.mutate(object.id)}>
              <IconRefresh />
              {t('card.header.recalculate')}
            </Button>
          )}
          {canManageSignals && (
            <Button loading={createSignal.isPending} onClick={handleCreateSignal}>
              <IconFilePlus />
              {t('card.header.createSignal')}
            </Button>
          )}
          {canEditRegistry && (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              <IconPencil />
              {t('card.header.edit')}
            </Button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <ZoneBadge zone={object.zone} score={object.score} size="md" />
        {object.key_status && <Chip>{keyStatusLabel(object.key_status, object.key_status_detail)}</Chip>}
        {object.is_demo && <DemoBadge />}
        <span className="text-sm text-text-3">
          {object.last_scored_at
            ? t('card.header.lastScored', { value: dateTime(object.last_scored_at) })
            : t('card.header.notScored')}
        </span>
        {object.next_check_at && (
          <span className="text-sm text-text-3">{t('card.header.nextCheck', { value: dateTime(object.next_check_at) })}</span>
        )}
        <Link to={`/signals?object_id=${object.id}`} className="text-sm text-text-3">
          {t('card.header.signals')}
        </Link>
      </div>

      <ZoneDisclaimer />

      {canEditRegistry && <ObjectFormModal opened={editing} onClose={() => setEditing(false)} object={object} />}
    </header>
  );
}
