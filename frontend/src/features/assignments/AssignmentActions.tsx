import { useState } from 'react';
import { IconCheck } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useUpdateAssignment } from '@/api/hooks/assignments';
import type { Assignment } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { TextArea } from '@/components/form/TextArea';
import { Button } from '@/components/ui/button';
import { FormDialog, FormFooter } from '@/features/objects/forms/fields';

function CompleteDialog({ assignment, onClose }: { assignment: Assignment; onClose: () => void }) {
  const { t } = useTranslation('assignments');
  const update = useUpdateAssignment();
  const [result, setResult] = useState('');
  const [touched, setTouched] = useState(false);
  const empty = result.trim() === '';

  return (
    <FormDialog opened onClose={onClose} title={t('complete.title')}>
      <form
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          setTouched(true);
          if (empty) return;
          update.mutate({ id: assignment.id, data: { status: 'done', result: result.trim() } }, { onSuccess: onClose });
        }}
      >
        <p className="mb-3 text-text-2">{assignment.task}</p>
        <TextArea
          label={t('complete.result')}
          required
          autoFocus
          maxLength={5000}
          value={result}
          onChange={(event) => setResult(event.target.value)}
          error={touched && empty ? t('required', { ns: 'common' }) : undefined}
        />
        <FormFooter loading={update.isPending} onCancel={onClose} submitLabel={t('complete.submit')} />
      </form>
    </FormDialog>
  );
}

/**
 * Buttons for an open assignment: complete (assignee, author, admin) and cancel (author, admin).
 * `compact` (task lists) shows only a quiet "Done" button; cancelling stays on the object page and /control.
 */
export function AssignmentActions({ assignment, compact = false }: { assignment: Assignment; compact?: boolean }) {
  const { t } = useTranslation('assignments');
  const { user, isAdmin } = useAuth();
  const update = useUpdateAssignment();
  const [completing, setCompleting] = useState(false);
  const [confirmingCancel, setConfirmingCancel] = useState(false);

  if (assignment.status !== 'open' || !user) return null;
  const isAuthor = user.id === assignment.author_id;
  const canComplete = isAuthor || isAdmin || user.id === assignment.assignee_id;
  const canCancel = isAuthor || isAdmin;

  if (compact) {
    if (!canComplete) return null;
    return (
      <>
        <Button
          variant="outline"
          className="min-h-11"
          aria-label={`${t('complete.action')}: ${assignment.task}`}
          onClick={() => setCompleting(true)}
        >
          <IconCheck />
          {t('complete.short')}
        </Button>
        {completing && <CompleteDialog assignment={assignment} onClose={() => setCompleting(false)} />}
      </>
    );
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      {canComplete && (
        <Button className="min-h-11" onClick={() => setCompleting(true)}>
          <IconCheck />
          {t('complete.action')}
        </Button>
      )}
      {canCancel &&
        (confirmingCancel ? (
          <>
            <span className="text-sm">{t('cancel.confirm')}</span>
            <Button
              variant="destructive"
              className="min-h-11"
              loading={update.isPending}
              onClick={() => update.mutate({ id: assignment.id, data: { status: 'cancelled' } })}
            >
              {t('cancel.confirmYes')}
            </Button>
            <Button variant="secondary" className="min-h-11" onClick={() => setConfirmingCancel(false)}>
              {t('cancel.no')}
            </Button>
          </>
        ) : (
          <Button variant="secondary" className="min-h-11" onClick={() => setConfirmingCancel(true)}>
            {t('cancel.action')}
          </Button>
        ))}
      {completing && <CompleteDialog assignment={assignment} onClose={() => setCompleting(false)} />}
    </div>
  );
}
