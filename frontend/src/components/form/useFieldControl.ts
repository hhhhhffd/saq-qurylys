import { useId, type ReactNode } from 'react';

/** Props every input of `components/form` shares (the names follow the Mantine inputs they replace). */
export interface FieldProps {
  id?: string;
  label?: ReactNode;
  /** hint under the label */
  description?: ReactNode;
  /** a message under the control; `true` only paints the control red */
  error?: ReactNode;
  /** shows the asterisk and sets `aria-required` (the form validates, the browser does not: forms use `noValidate`) */
  required?: boolean;
  /** goes to the wrapper (layout: `col-span-2`, widths …) */
  className?: string;
}

/** Ids and aria attributes that tie a control to its label, hint and error. Spread `controlProps` on the control. */
export function useFieldControl({ id, description, error, required }: Pick<FieldProps, 'id' | 'description' | 'error' | 'required'>) {
  const generated = useId();
  const controlId = id ?? generated;
  const hasMessage = error !== undefined && error !== null && typeof error !== 'boolean';
  const describedBy = [description ? `${controlId}-description` : null, hasMessage && error ? `${controlId}-error` : null].filter(Boolean).join(' ');
  return {
    id: controlId,
    labelId: `${controlId}-label`,
    controlProps: {
      id: controlId,
      'aria-invalid': error ? (true as const) : undefined,
      'aria-required': required || undefined,
      'aria-describedby': describedBy || undefined,
    },
  };
}
