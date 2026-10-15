import { useState } from 'react';
import { Button } from '@mantine/core';
import { IconArrowLeft, IconFilePlus, IconPencil, IconRefresh } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link, useNavigate } from 'react-router';
import { useRecalculateObject } from '@/api/hooks/objects';
import { useCreateSignal } from '@/api/hooks/signals';
import type { ObjectDetail } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Chip } from '@/components/Chip';
import { ZoneBadge } from '@/components/Zone';
import { ZoneDisclaimer } from '@/components/ZoneDisclaimer';
import { useFormat } from '@/i18n/useFormat';
import { useKeyStatusLabel } from '@/i18n/useEnum';
import { ObjectFormModal } from '../forms/ObjectFormModal';
import classes from './ObjectHeader.module.css';

export function ObjectHeader({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('objects');
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
    <header className={classes.root}>
      <Link to="/objects" className={classes.back}>
        <IconArrowLeft size={16} stroke={1.8} aria-hidden />
        {t('card.back')}
      </Link>

      <div className={classes.titleRow}>
        <div className={classes.titleBlock}>
          <p className={classes.code}>{object.code}</p>
          <h1 className={classes.title}>{object.name}</h1>
        </div>
        <div className={classes.actions}>
          {canEditRegistry && (
            <Button
              variant="default"
              leftSection={<IconRefresh size={16} />}
              loading={recalculate.isPending}
              onClick={() => recalculate.mutate(object.id)}
            >
              {t('card.header.recalculate')}
            </Button>
          )}
          {canManageSignals && (
            <Button
              leftSection={<IconFilePlus size={16} />}
              loading={createSignal.isPending}
              onClick={handleCreateSignal}
            >
              {t('card.header.createSignal')}
            </Button>
          )}
          {canEditRegistry && (
            <Button variant="default" leftSection={<IconPencil size={16} />} onClick={() => setEditing(true)}>
              {t('card.header.edit')}
            </Button>
          )}
        </div>
      </div>

      <div className={classes.status}>
        <ZoneBadge zone={object.zone} score={object.score} size="md" />
        {object.key_status && <Chip>{keyStatusLabel(object.key_status, object.key_status_detail)}</Chip>}
        {object.is_demo && <Chip tone="info">{t('card.demo')}</Chip>}
        <span className={classes.meta}>
          {object.last_scored_at
            ? t('card.header.lastScored', { value: dateTime(object.last_scored_at) })
            : t('card.header.notScored')}
        </span>
        {object.next_check_at && (
          <span className={classes.meta}>{t('card.header.nextCheck', { value: dateTime(object.next_check_at) })}</span>
        )}
        <Link to={`/signals?object_id=${object.id}`} className={classes.meta}>
          {t('card.header.signals')}
        </Link>
      </div>

      <ZoneDisclaimer />

      {canEditRegistry && <ObjectFormModal opened={editing} onClose={() => setEditing(false)} object={object} />}
    </header>
  );
}
