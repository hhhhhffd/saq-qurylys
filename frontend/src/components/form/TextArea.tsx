import type { ComponentProps } from 'react';
import { InputWrapper } from '@/components/form/InputWrapper';
import { useFieldControl, type FieldProps } from '@/components/form/useFieldControl';
import { Textarea } from '@/components/ui/textarea';

type TextAreaProps = FieldProps &
  Omit<ComponentProps<typeof Textarea>, keyof FieldProps | 'children'> & {
    /** lines shown when empty (default 3) */
    minRows?: number;
    /** the field grows with its text up to this many lines, then scrolls */
    maxRows?: number;
  };

/** Auto-growing multi-line field (replaces the Mantine `Textarea` with `autosize`). */
export function TextArea({ id, label, description, error, required, className, minRows = 3, maxRows, style, ...props }: TextAreaProps) {
  const field = useFieldControl({ id, description, error, required });
  return (
    <InputWrapper field={field} label={label} description={description} error={error} required={required} className={className}>
      <Textarea
        {...field.controlProps}
        style={{ minHeight: `calc(${minRows}lh + 0.75rem + 2px)`, maxHeight: maxRows ? `calc(${maxRows}lh + 0.75rem + 2px)` : undefined, ...style }}
        {...props}
      />
    </InputWrapper>
  );
}
