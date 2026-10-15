import { useState } from 'react';
import { IconCheck, IconPencil, IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useUpdateComplaint } from '@/api/hooks/objects';
import type { Complaint, ComplaintStatus, ObjectDetail } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Chip, type ChipTone } from '@/components/Chip';
import { Panel } from '@/components/Panel';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { cn } from '@/lib/utils';
import { ComplaintFormModal } from '../forms/ComplaintFormModal';
import { anchorId } from '@/components/risk/anchors';
import { anchorTargetClass } from './styles';

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
          <Button variant="secondary" size="sm" onClick={() => setModal({ opened: true })}>
            <IconPlus />
            {t('card.complaints.add')}
          </Button>
        )
      }
    >
      {complaints.length === 0 ? (
        <p className="px-4 pb-4 text-text-3">{t('card.complaints.empty')}</p>
      ) : (
        <ul>
          {complaints.map((item) => (
            <li
              key={item.id}
              id={anchorId('complaint', item.id)}
              className={cn('border-t border-border px-4 py-3 first:border-t-0', anchorTargetClass)}
            >
              <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
                <strong className="tabular-nums">{date(item.received_at)}</strong>
                <span className="text-text-3">
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
                  <span className="ml-auto inline-flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="xs"
                      title={t('card.complaints.verifiedHint')}
                      loading={updateComplaint.isPending && updateComplaint.variables.id === item.id}
                      onClick={() => updateComplaint.mutate({ id: item.id, data: { is_verified: !item.is_verified } })}
                    >
                      {item.is_verified ? t('card.complaints.unmarkVerified') : t('card.complaints.markVerified')}
                    </Button>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={t('card.complaints.edit')}
                          onClick={() => setModal({ opened: true, complaint: item })}
                        >
                          <IconPencil />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>{t('card.complaints.edit')}</TooltipContent>
                    </Tooltip>
                  </span>
                )}
              </div>
              {item.summary && <p className="mt-2 text-text-2 [overflow-wrap:anywhere]">{item.summary}</p>}
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
