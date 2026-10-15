import { useState } from 'react';
import { ActionIcon, Button, Tooltip } from '@mantine/core';
import { IconPencil, IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import type { Complaint, ComplaintStatus, ObjectDetail } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Chip, type ChipTone } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { ComplaintFormModal } from '../forms/ComplaintFormModal';
import { anchorId } from './anchors';
import classes from './Section.module.css';

const STATUS_TONE: Record<ComplaintStatus, ChipTone> = { new: 'yellow', in_review: 'info', closed: 'neutral' };

interface ModalState {
  opened: boolean;
  complaint?: Complaint;
}

export function ComplaintsSection({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const { date } = useFormat();
  const { canEditRegistry } = useAuth();
  const [modal, setModal] = useState<ModalState>({ opened: false });

  const complaints = [...object.complaints].sort(
    (a, b) => new Date(b.received_at).getTime() - new Date(a.received_at).getTime() || b.id - a.id,
  );

  return (
    <Panel
      title={t('card.complaints.title')}
      id="complaints"
      flush
      actions={
        canEditRegistry && (
          <Button
            variant="default"
            size="xs"
            leftSection={<IconPlus size={14} />}
            onClick={() => setModal({ opened: true })}
          >
            {t('card.complaints.add')}
          </Button>
        )
      }
    >
      {complaints.length === 0 ? (
        <p className={`${classes.muted} ${classes.pad}`}>{t('card.complaints.empty')}</p>
      ) : (
        <ul className={classes.list}>
          {complaints.map((item) => (
            <li key={item.id} id={anchorId('complaint', item.id)} className={`${classes.item} ${classes.target}`}>
              <div className={classes.itemHead}>
                <strong className="tnum">{date(item.received_at)}</strong>
                <span className="muted">
                  {e('complaint_source', item.source)}
                  {item.external_id && ` · ${item.external_id}`}
                </span>
                <Chip tone={STATUS_TONE[item.status]}>{e('complaint_status', item.status)}</Chip>
                {item.is_collective && (
                  <Chip outline>
                    {item.signatories_count > 0
                      ? t('card.complaints.collective', { count: item.signatories_count })
                      : t('card.complaints.collectiveNoCount')}
                  </Chip>
                )}
                {item.confirmed_payments && <Chip tone="red">{t('card.complaints.confirmedPayments')}</Chip>}
                {canEditRegistry && (
                  <span className={classes.itemAction}>
                    <Tooltip label={t('card.complaints.edit')}>
                      <ActionIcon
                        variant="subtle"
                        color="gray"
                        aria-label={t('card.complaints.edit')}
                        onClick={() => setModal({ opened: true, complaint: item })}
                      >
                        <IconPencil size={16} />
                      </ActionIcon>
                    </Tooltip>
                  </span>
                )}
              </div>
              {item.summary && <p className={classes.text}>{item.summary}</p>}
            </li>
          ))}
        </ul>
      )}

      {canEditRegistry && (
        <ComplaintFormModal
          opened={modal.opened}
          onClose={() => setModal((state) => ({ ...state, opened: false }))}
          objectId={object.id}
          complaint={modal.complaint}
        />
      )}
    </Panel>
  );
}
