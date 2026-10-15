import { IconX } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { InputWrapper } from '@/components/form/InputWrapper';
import { useFieldControl, type FieldProps } from '@/components/form/useFieldControl';
import { Combobox, type ComboboxOption } from '@/components/ui/combobox';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export type SelectOption = ComboboxOption;

interface SelectInputProps extends FieldProps {
  data: SelectOption[];
  value: string | null;
  onChange: (value: string | null) => void;
  placeholder?: string;
  disabled?: boolean;
  name?: string;
  /** a button that sets the value back to `null` */
  clearable?: boolean;
  /** type to filter (a text field with a list); without it a plain select */
  searchable?: boolean;
  /** server-side search, see `Combobox`. Implies `searchable` */
  onSearchChange?: (text: string) => void;
  loading?: boolean;
  nothingFound?: React.ReactNode;
}

/**
 * Single select with label, hint and error (replaces the Mantine `Select`). Values are strings; `null` is "nothing
 * chosen". Both variants expose `role="combobox"` named by the label and `role="option"` items.
 */
export function SelectInput({
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
  searchable,
  onSearchChange,
  loading,
  nothingFound,
}: SelectInputProps) {
  const { t } = useTranslation();
  const field = useFieldControl({ id, description, error, required });

  return (
    <InputWrapper field={field} label={label} description={description} error={error} required={required} className={className}>
      {searchable || onSearchChange ? (
        <Combobox
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
      ) : (
        <div className="relative">
          <Select value={value ?? ''} onValueChange={(next) => onChange(next)} disabled={disabled} name={name}>
            <SelectTrigger {...field.controlProps} className={clearable && value ? 'pr-12' : undefined}>
              <SelectValue placeholder={placeholder} />
            </SelectTrigger>
            <SelectContent>
              {data.map((option) => (
                <SelectItem key={option.value} value={option.value} disabled={option.disabled}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {clearable && value && !disabled && (
            <button
              type="button"
              aria-label={t('ui.clear')}
              className="absolute top-1/2 right-6 grid size-5 -translate-y-1/2 place-items-center rounded-[2px] text-text-3 hover:bg-hover hover:text-text"
              onClick={() => onChange(null)}
            >
              <IconX className="size-3.5" />
            </button>
          )}
        </div>
      )}
    </InputWrapper>
  );
}
