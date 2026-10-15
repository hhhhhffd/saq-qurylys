import { useState } from 'react';
import { ActionIcon, Button, Tooltip } from '@mantine/core';
import { IconCheck, IconPencil, IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useUpdateComplaint } from '@/api/hooks/objects';
import type { Complaint, ComplaintStatus, ObjectDetail } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Chip, type ChipTone } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { ComplaintFormModal } from '../forms/ComplaintFormModal';
import { anchorId } from '@/components/risk/anchors';
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
  const updateComplaint = useUpdateComplaint();
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
                {item.is_verified ? (
                  <Chip
                    tone="green"
                    title={
                      item.verified_at ? t('card.complaints.verifiedBy', { value: date(item.verified_at) }) : undefined
                    }
                  >
                    <IconCheck size={12} stroke={2.4} aria-hidden />
                    {t('card.complaints.verified')}
                  </Chip>
                ) : (
                  <Chip outline>{t('card.complaints.unverified')}</Chip>
                )}
                {canEditRegistry && (
                  <span className={classes.itemAction}>
                    <Button
                      variant="subtle"
                      size="compact-xs"
                      color="gray"
                      title={t('card.complaints.verifiedHint')}
                      loading={updateComplaint.isPending && updateComplaint.variables.id === item.id}
                      onClick={() => updateComplaint.mutate({ id: item.id, data: { is_verified: !item.is_verified } })}
                    >
                      {item.is_verified ? t('card.complaints.unmarkVerified') : t('card.complaints.markVerified')}
                    </Button>
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
