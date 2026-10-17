import { IconAlertTriangle, IconArrowLeft, IconCheck, IconChevronDown, IconMessage } from '@tabler/icons-react';
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
  const currentStep = status === 'sent' ? 2 : status === 'responded' ? 3 : status === 'closed' ? null : 0;

  let nextStepTitle: string;
  let nextStepCopy: string;
  if (status === 'closed') {
    nextStepTitle = t('detail.next.doneTitle');
    nextStepCopy = t('detail.next.doneCopy');
  } else if (isRecipient && status === 'sent') {
    nextStepTitle = t('detail.next.recipientTitle');
    nextStepCopy = t('detail.next.recipientCopy');
  } else if (isRecipient && status === 'responded') {
    nextStepTitle = t('detail.next.recipientRespondedTitle');
    nextStepCopy = t('detail.next.recipientRespondedCopy');
  } else if (!canManageSignals) {
    nextStepTitle = t('detail.next.readOnlyTitle');
    nextStepCopy = t('detail.next.readOnlyCopy');
  } else if (status === 'requires_confirmation') {
    nextStepTitle = t('detail.next.prepareTitle');
    nextStepCopy = t('detail.next.prepareCopy');
  } else if (status === 'returned') {
    nextStepTitle = t('detail.next.returnTitle');
    nextStepCopy = t('detail.next.returnCopy');
  } else if (status === 'sent' && detail.recipient === 'mio') {
    nextStepTitle = t('detail.next.recipientTitle');
    nextStepCopy = t('detail.next.recipientCopy');
  } else if (status === 'sent') {
    nextStepTitle = t('detail.next.waitingTitle');
    nextStepCopy = t('detail.next.waitingCopy', { recipient: e('recipient', detail.recipient) });
  } else {
    nextStepTitle = t('detail.next.reviewTitle');
    nextStepCopy = t('detail.next.reviewCopy');
  }

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
    <div className="flex flex-col gap-4">
      <Link to="/signals" className="inline-flex min-h-11 items-center gap-1 self-start px-1 text-sm text-link hover:underline">
        <IconArrowLeft size={16} aria-hidden />
        {t('detail.back')}
      </Link>
      <PageHeader
        title={detail.number}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
            <SignalStatusChip status={status} />
            {detail.is_overdue && <Chip tone="red">{t('due.overdue')}</Chip>}
            <span>{e('origin', detail.origin)}</span>
            {sections.is_demo && <DemoBadge />}
          </span>
        }
        actions={<ActionsBar detail={detail} recipient={draft.value.recipient} dirty={draft.dirty} canSave={draft.valid} />}
      />

      <section className="rounded border border-border-strong bg-surface p-3 sm:p-4" aria-labelledby="signal-next-step">
        <p className="mb-2 text-xs font-semibold tracking-wide text-text-2 uppercase">{t('detail.workflow.label')}</p>
        <ol aria-label={t('detail.workflow.label')} className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {(['prepare', 'send', 'answer', 'close'] as const).map((step, index) => {
            const complete = status === 'closed' || (currentStep !== null && index < currentStep);
            const current = currentStep !== null && index === currentStep;
            return (
              <li
                key={step}
                aria-current={current ? 'step' : undefined}
                className={
                  complete
                    ? 'flex min-h-11 items-center gap-2 rounded border border-zone-green/40 bg-zone-green-bg px-2 text-sm font-medium text-zone-green-ink'
                    : current
                      ? 'flex min-h-11 items-center gap-2 rounded border border-primary bg-surface px-2 text-sm font-semibold text-text'
                      : 'flex min-h-11 items-center gap-2 rounded border border-border bg-surface-sunken px-2 text-sm text-text-3'
                }
              >
                <span
                  aria-hidden="true"
                  className={
                    complete
                      ? 'grid size-5 shrink-0 place-items-center rounded-full bg-zone-green-bg'
                      : current
                        ? 'grid size-5 shrink-0 place-items-center rounded-full bg-primary text-primary-foreground'
                        : 'grid size-5 shrink-0 place-items-center rounded-full border border-border-strong text-xs'
                  }
                >
                  {complete ? <IconCheck size={14} /> : index + 1}
                </span>
                <span>{t(`detail.workflow.steps.${step}`)}</span>
              </li>
            );
          })}
        </ol>
        <div className="mt-3 border-t border-border pt-3">
          <p className="text-xs font-semibold tracking-wide text-text-2 uppercase">{t('detail.nextStep')}</p>
          <h2 id="signal-next-step" className="mt-1 text-base font-semibold text-text">{nextStepTitle}</h2>
          <p className="mt-1 text-sm text-text-2">{nextStepCopy}</p>
          {canManageSignals && status === 'requires_confirmation' && (
            <ul className="mt-2 flex flex-col gap-1 text-sm text-text-2">
              {!draft.value.recipient && <li>{t('actions.needRecipient')}</li>}
              {draft.dirty && !draft.valid && <li className="text-zone-red-ink">{t('unsaved.invalid')}</li>}
              {draft.dirty && draft.valid && <li>{t('actions.saveFirst')}</li>}
            </ul>
          )}
          {canManageSignals && status === 'returned' && draft.dirty && (
            <p className="mt-2 text-sm text-text-2">
              {draft.valid ? t('detail.next.saveReturned') : t('unsaved.invalid')}
            </p>
          )}
          {status === 'sent' && detail.due_date && (
            <p className="mt-2 text-sm text-text">
              <strong>{t('detail.next.deadline')}: </strong>
              <DueInfo dueDate={detail.due_date} status={status} isOverdue={detail.is_overdue} />
            </p>
          )}
        </div>
      </section>

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
                <Link to={`/objects/${detail.object_id}`} className="text-link hover:underline">{detail.object_name}</Link>
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
        <ZoneDisclaimer className="mt-3.5 border-t border-border pt-3" />
      </Panel>

      <section aria-labelledby="signal-materials-heading" className="grid min-w-0 gap-4">
        <h2 id="signal-materials-heading" className="text-sm font-semibold text-text">
          {t('detail.groups.materials')}
        </h2>
        <div className="grid min-w-0 grid-cols-1 items-start gap-4 xl:grid-cols-2">
          <ObjectDeveloperSection data={sections.object_developer} />
          <RiskFactorsSection sections={sections} linked={!isRecipient} />
          <PermitChecksSection items={sections.permit_checks} />
          <PublicationsSection items={sections.publications} showAdLinks={!isRecipient} />
        </div>
      </section>

      <section aria-labelledby="signal-review-heading" className="grid min-w-0 gap-4">
        <h2 id="signal-review-heading" className="text-sm font-semibold text-text">
          {t('detail.groups.review')}
        </h2>
        <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-2">
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
          <NoteSection value={draft.value.note} editable={editable} onChange={(next) => draft.update({ note: next })} />
        </div>
      </section>

      <section aria-labelledby="signal-route-heading" className="grid min-w-0 gap-4">
        <h2 id="signal-route-heading" className="text-sm font-semibold text-text">
          {t('detail.groups.route')}
        </h2>
        <RouteSection detail={detail} value={draft.value} editable={editable} onChange={draft.update} />
      </section>

      {!isRecipient && (
        <details className="group rounded border border-border bg-surface">
          <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 px-3 text-sm font-medium text-text-2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-focus">
            {t('detail.historySummary')}
            <IconChevronDown size={16} aria-hidden className="shrink-0 transition-transform group-open:rotate-180 motion-reduce:transition-none" />
          </summary>
          <div className="border-t border-border p-3">
            <AuditTimeline entries={detail.audit} />
          </div>
        </details>
      )}

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
