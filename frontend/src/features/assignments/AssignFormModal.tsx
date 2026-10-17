import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAssignees, useCreateAssignment } from '@/api/hooks/assignments';
import { DateInput } from '@/components/form/DateInput';
import { SelectInput } from '@/components/form/SelectInput';
import { TextArea } from '@/components/form/TextArea';
import { FormDialog, FormFooter } from '@/features/objects/forms/fields';
import { today } from '@/features/objects/forms/utils';

interface Props {
  opened: boolean;
  onClose: () => void;
  objectId: number;
}

export function AssignFormModal({ opened, onClose, objectId }: Props) {
  const { t } = useTranslation('assignments');
  return (
    <FormDialog opened={opened} onClose={onClose} title={t('form.title')}>
      <AssignForm objectId={objectId} onClose={onClose} />
    </FormDialog>
  );
}

function AssignForm({ objectId, onClose }: Omit<Props, 'opened'>) {
  const { t } = useTranslation('assignments');
  const { t: tc } = useTranslation('common');
  const assignees = useAssignees(objectId, true);
  const create = useCreateAssignment(objectId);
  const [assigneeId, setAssigneeId] = useState<string | null>(null);
  const [dueDate, setDueDate] = useState<string | null>(null);
  const [task, setTask] = useState(t('form.defaultTask'));
  const [touched, setTouched] = useState(false);

  const options = (assignees.data ?? []).map((user) => ({ value: String(user.id), label: user.full_name }));
  const taskEmpty = task.trim() === '';
  const pastDate = dueDate !== null && dueDate < today();

  const submit = () => {
    setTouched(true);
    if (assigneeId === null || dueDate === null || pastDate || taskEmpty) return;
    create.mutate({ assignee_id: Number(assigneeId), due_date: dueDate, task: task.trim() }, { onSuccess: onClose });
  };

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
      className="grid gap-3"
    >
      <SelectInput
        label={t('form.assignee')}
        required
        searchable
        data={options}
        value={assigneeId}
        onChange={setAssigneeId}
        placeholder={t('form.assigneePlaceholder')}
        nothingFound={t('form.noAssignees')}
        error={touched && assigneeId === null ? tc('required') : undefined}
      />
      <DateInput
        label={t('form.due')}
        required
        value={dueDate}
        onChange={setDueDate}
        minDate={today()}
        placeholder="ДД.ММ.ГГГГ"
        error={touched && dueDate === null ? tc('required') : pastDate ? t('form.pastDate') : undefined}
      />
      <TextArea
        label={t('form.task')}
        required
        maxLength={2000}
        value={task}
        onChange={(event) => setTask(event.target.value)}
        error={touched && taskEmpty ? tc('required') : undefined}
      />
      <FormFooter loading={create.isPending} onCancel={onClose} submitLabel={t('form.submit')} />
    </form>
  );
}
