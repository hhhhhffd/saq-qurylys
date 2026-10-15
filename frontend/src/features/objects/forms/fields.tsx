import type { ReactNode } from 'react';
import { Controller, type Control, type FieldValues, type Path } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { DateInput } from '@/components/form/DateInput';
import { NumberInput } from '@/components/form/NumberInput';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import type { CoordinateValue } from './utils';

interface FormDialogProps {
  opened: boolean;
  onClose: () => void;
  title: string;
  /** wider window for the long forms */
  wide?: boolean;
  children: ReactNode;
}

/**
 * Window of a form. A click outside does not close it (a half filled form is easy to lose); Escape and the cross do.
 * The form is mounted together with the body, so every opening starts from fresh values.
 */
export function FormDialog({ opened, onClose, title, wide = true, children }: FormDialogProps) {
  return (
    <Dialog open={opened} onOpenChange={(next) => !next && onClose()}>
      <DialogContent
        className={cn(wide && 'sm:max-w-lg')}
        aria-describedby={undefined}
        onInteractOutside={(event) => event.preventDefault()}
      >
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        {children}
      </DialogContent>
    </Dialog>
  );
}

/** Two-column grid of the form fields (one column on a phone). */
export function FormGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-3 sm:grid-cols-2">{children}</div>;
}

/** A field that spans both columns of the grid. */
export const fullWidth = 'sm:col-span-2';

/** `DateInput` with the `DD.MM.YYYY` placeholder; stores `YYYY-MM-DD`. */
export function DateField(props: React.ComponentProps<typeof DateInput>) {
  const { t } = useTranslation('objectForms');
  return <DateInput placeholder={t('datePlaceholder')} {...props} />;
}

/** Latitude and longitude as two grid cells; pair them with `checkCoordinates` in the form's schema. */
export function CoordinateFields<T extends FieldValues & Record<'lat' | 'lon', CoordinateValue>>({
  control,
}: {
  control: Control<T>;
}) {
  const { t } = useTranslation('objectForms');
  return (
    <>
      {(['lat', 'lon'] as const).map((name) => (
        <Controller
          key={name}
          control={control}
          name={name as Path<T>}
          render={({ field, fieldState }) => (
            <NumberInput
              label={t(name)}
              placeholder={name === 'lat' ? '51.128200' : '71.430400'}
              decimalScale={6}
              hideControls
              name={field.name}
              value={field.value as CoordinateValue}
              onChange={field.onChange}
              onBlur={field.onBlur}
              error={fieldState.error?.message}
            />
          )}
        />
      ))}
    </>
  );
}

interface FormFooterProps {
  loading: boolean;
  onCancel: () => void;
  submitLabel: string;
  submitDisabled?: boolean;
}

/** Cancel and submit, aligned right. The submit button belongs to the surrounding `<form>`. */
export function FormFooter({ loading, onCancel, submitLabel, submitDisabled }: FormFooterProps) {
  const { t } = useTranslation();
  return (
    <DialogFooter className="mt-3">
      <Button type="button" variant="secondary" onClick={onCancel} disabled={loading}>
        {t('cancel')}
      </Button>
      <Button type="submit" loading={loading} disabled={submitDisabled}>
        {submitLabel}
      </Button>
    </DialogFooter>
  );
}
