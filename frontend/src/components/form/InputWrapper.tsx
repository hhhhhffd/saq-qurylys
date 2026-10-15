import type { ReactNode } from 'react';
import type { FieldProps, useFieldControl } from '@/components/form/useFieldControl';
import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field';

/** Label (with asterisk), hint, the control, error message. Use `useFieldControl` for the ids. */
export function InputWrapper({
  field,
  label,
  description,
  error,
  required,
  className,
  children,
}: Pick<FieldProps, 'label' | 'description' | 'error' | 'required' | 'className'> & {
  field: ReturnType<typeof useFieldControl>;
  children: ReactNode;
}) {
  return (
    <Field className={className} data-invalid={error ? true : undefined}>
      {label && (
        <FieldLabel id={field.labelId} htmlFor={field.id}>
          {label}
          {required && (
            <span aria-hidden className="text-accent-text">
              {' *'}
            </span>
          )}
        </FieldLabel>
      )}
      {description && <FieldDescription id={`${field.id}-description`}>{description}</FieldDescription>}
      {children}
      {typeof error !== 'boolean' && error && <FieldError id={`${field.id}-error`}>{error}</FieldError>}
    </Field>
  );
}
