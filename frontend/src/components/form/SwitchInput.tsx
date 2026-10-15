import type { ComponentProps } from 'react';
import { useFieldControl, type FieldProps } from '@/components/form/useFieldControl';
import { Field, FieldContent, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field';
import { Switch } from '@/components/ui/switch';

type SwitchInputProps = Pick<FieldProps, 'id' | 'label' | 'description' | 'error' | 'className'> &
  Omit<ComponentProps<typeof Switch>, keyof FieldProps | 'children'>;

/** Switch with its label and hint beside it (replaces the Mantine `Switch`). Controlled: `checked` + `onCheckedChange`. */
export function SwitchInput({ id, label, description, error, className, ...props }: SwitchInputProps) {
  const field = useFieldControl({ id, description, error });
  return (
    <Field orientation="horizontal" className={className} data-invalid={error ? true : undefined}>
      <Switch {...field.controlProps} {...props} />
      <FieldContent>
        {label && <FieldLabel htmlFor={field.id}>{label}</FieldLabel>}
        {description && <FieldDescription id={`${field.id}-description`}>{description}</FieldDescription>}
        {typeof error !== 'boolean' && error && <FieldError id={`${field.id}-error`}>{error}</FieldError>}
      </FieldContent>
    </Field>
  );
}
