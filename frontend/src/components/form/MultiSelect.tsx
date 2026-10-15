import type { ReactNode } from 'react';
import { InputWrapper } from '@/components/form/InputWrapper';
import { useFieldControl, type FieldProps } from '@/components/form/useFieldControl';
import type { SelectOption } from '@/components/form/SelectInput';
import { MultiCombobox } from '@/components/ui/combobox';

interface MultiSelectProps extends FieldProps {
  data: SelectOption[];
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  disabled?: boolean;
  name?: string;
  /** a button that empties the selection */
  clearable?: boolean;
  /** server-side search, see `Combobox` */
  onSearchChange?: (text: string) => void;
  loading?: boolean;
  nothingFound?: ReactNode;
}

/** Multi select with chips and a filterable list (replaces the Mantine `MultiSelect`). */
export function MultiSelect({
  id,
  label,
  description,
  error,
  required,
  className,
  data,
  value,
  onChange,
  placeholder,
  disabled,
  name,
  clearable,
  onSearchChange,
  loading,
  nothingFound,
}: MultiSelectProps) {
  const field = useFieldControl({ id, description, error, required });
  return (
    <InputWrapper field={field} label={label} description={description} error={error} required={required} className={className}>
      <MultiCombobox
        {...field.controlProps}
        options={data}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        disabled={disabled}
        name={name}
        clearable={clearable}
        onSearchChange={onSearchChange}
        loading={loading}
        emptyText={nothingFound}
      />
    </InputWrapper>
  );
}
