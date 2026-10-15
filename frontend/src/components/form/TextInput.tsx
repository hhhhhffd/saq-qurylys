import type { ComponentProps } from 'react';
import { InputWrapper } from '@/components/form/InputWrapper';
import { useFieldControl, type FieldProps } from '@/components/form/useFieldControl';
import { Input } from '@/components/ui/input';

type TextInputProps = FieldProps & Omit<ComponentProps<typeof Input>, keyof FieldProps | 'children'>;

/** Text field with label, hint and error (replaces the Mantine `TextInput`). Native input props pass through. */
export function TextInput({ id, label, description, error, required, className, ...props }: TextInputProps) {
  const field = useFieldControl({ id, description, error, required });
  return (
    <InputWrapper field={field} label={label} description={description} error={error} required={required} className={className}>
      <Input {...field.controlProps} {...props} />
    </InputWrapper>
  );
}
