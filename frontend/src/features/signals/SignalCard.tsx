import { IconAlertTriangle, IconArrowLeft, IconMessage } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { useUpdateSignal } from '@/api/hooks/signals';
import type { SignalDetail } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Chip } from '@/components/Chip';
import { DemoBadge } from '@/components/DemoBadge';
import { KeyValue } from '@/components/KeyValue';
import { PageHeader } from '@/components/PageHeader';
import { Panel } from '@/components/Panel';
import { ZoneBadge } from '@/components/Zone';
import { ZoneDisclaimer } from '@/components/ZoneDisclaimer';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { ActionsBar } from './ActionsBar';
import { AuditTimeline } from './AuditTimeline';
import { Callout } from './Callout';
import { DueInfo } from './DueInfo';
import { SignalStatusChip } from './SignalStatusChip';
import { UnsavedBar } from './UnsavedBar';
import { useApplySignal } from './useApplySignal';
import { useSignalDraft } from './useSignalDraft';
import { NoteSection } from './sections/NoteSection';
import { ObjectDeveloperSection } from './sections/ObjectDeveloperSection';
import { PermitChecksSection } from './sections/PermitChecksSection';
import { ProposedMeasuresSection } from './sections/ProposedMeasuresSection';
import { PublicationsSection } from './sections/PublicationsSection';
import { RiskFactorsSection } from './sections/RiskFactorsSection';
import { RouteSection } from './sections/RouteSection';
import { SchemePaymentsSection } from './sections/SchemePaymentsSection';
import classes from './SignalCard.module.css';

export function SignalCard({ detail }: { detail: SignalDetail }) {
  const { t } = useTranslation('signals');
  const { canManageSignals, isRecipient } = useAuth();
  const e = useEnum();
  const { dateTime } = useFormat();
  const draft = useSignalDraft(detail);
  const update = useUpdateSignal();
  const apply = useApplySignal();
  const { sections, status } = detail;

  const editable = canManageSignals && (status === 'requires_confirmation' || status === 'returned');
  const hasResponse = (status === 'responded' || status === 'closed') && detail.response_text;

  const save = () =>
    update.mutate(
      { id: detail.id, data: draft.toPatch() },
      {
        onSuccess: (next) => {
          apply(next);
          draft.reset();
        },
      },
    );

  return (
    <div className={classes.page}>
      <Link to="/signals" className={classes.back}>
        <IconArrowLeft size={16} aria-hidden />
        {t('detail.back')}
      </Link>
      <PageHeader
        title={detail.number}
        subtitle={
          <span className={classes.badges}>
            <SignalStatusChip status={status} />
            {detail.is_overdue && <Chip tone="red">{t('due.overdue')}</Chip>}
            <span>{e('origin', detail.origin)}</span>
            {sections.is_demo && <DemoBadge />}
          </span>
        }
        actions={<ActionsBar detail={detail} recipient={draft.value.recipient} dirty={draft.dirty} />}
      />

      {status === 'returned' && detail.return_comment && (
        <Callout
          tone="warning"
          icon={<IconAlertTriangle size={18} />}
          title={t('detail.returnComment')}
          meta={canManageSignals && t('detail.returnedHint')}
          multiline
        >
          {detail.return_comment}
        </Callout>
      )}
      {hasResponse && (
        <Callout
          icon={<IconMessage size={18} />}
          title={t('detail.response')}
          meta={detail.response_at && t('detail.responseAt', { value: dateTime(detail.response_at) })}
          multiline
        >
          {detail.response_text}
        </Callout>
      )}

      <Panel title={t('detail.summary')}>
        <KeyValue
          columns={3}
          items={[
            {
              label: t('detail.fields.object'),
              value: isRecipient ? (
                detail.object_name
              ) : (
                <Link to={`/objects/${detail.object_id}`}>{detail.object_name}</Link>
              ),
            },
            { label: t('detail.fields.zone'), value: <ZoneBadge zone={detail.zone} size="md" /> },
            { label: t('detail.fields.recipient'), value: e('recipient', detail.recipient) },
            { label: t('detail.fields.reviewDays'), value: t('reviewDays', { count: detail.review_days }) },
            { label: t('detail.fields.sentAt'), value: detail.sent_at && dateTime(detail.sent_at) },
            {
              label: t('detail.fields.due'),
              value: detail.due_date && (
                <DueInfo dueDate={detail.due_date} status={status} isOverdue={detail.is_overdue} />
              ),
            },
            { label: t('detail.fields.createdAt'), value: dateTime(detail.created_at) },
          ]}
        />
        <ZoneDisclaimer className={classes.summaryFoot} />
      </Panel>

      <ObjectDeveloperSection data={sections.object_developer} />
      <RiskFactorsSection sections={sections} linked={!isRecipient} />
      <PermitChecksSection items={sections.permit_checks} />
      <PublicationsSection items={sections.publications} showAdLinks={!isRecipient} />
      <div className={classes.pair}>
        <SchemePaymentsSection
          value={draft.value.scheme_payments}
          editable={editable}
          onChange={(next) => draft.update({ scheme_payments: next })}
        />
        <ProposedMeasuresSection
          value={draft.value.proposed_measures}
          editable={editable}
          onChange={(next) => draft.update({ proposed_measures: next })}
        />
        <RouteSection detail={detail} value={draft.value} editable={editable} onChange={draft.update} />
        <NoteSection value={draft.value.note} editable={editable} onChange={(next) => draft.update({ note: next })} />
      </div>

      {!isRecipient && <AuditTimeline entries={detail.audit} />}

      {draft.dirty && (
        <UnsavedBar
          returned={status === 'returned'}
          saving={update.isPending}
          canSave={draft.valid}
          onSave={save}
          onDiscard={draft.reset}
        />
      )}
    </div>
  );
}
