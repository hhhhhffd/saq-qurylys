import { useRef, type ComponentProps, type ReactNode } from 'react';
import { IconUpload, IconX } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { InputWrapper } from '@/components/form/InputWrapper';
import { useFieldControl, type FieldProps } from '@/components/form/useFieldControl';
import { cn } from '@/lib/utils';
import { controlClass } from '@/components/ui/styles';

type Common = FieldProps &
  Omit<ComponentProps<'input'>, keyof FieldProps | 'value' | 'onChange' | 'type' | 'multiple' | 'children' | 'placeholder'> & {
    placeholder?: string;
    /** icon before the file names; the upload icon by default */
    leftSection?: ReactNode;
    /** a button that empties the field */
    clearable?: boolean;
  };

type FileInputProps = Common &
  (
    | { multiple?: false; value: File | null; onChange: (file: File | null) => void }
    | { multiple: true; value: File[]; onChange: (files: File[]) => void }
  );

/**
 * File picker that looks like a field (replaces the Mantine `FileInput`). The chosen files are `value`; the native
 * input is emptied after every pick, so the same file can be picked again and `value={[]}` works as an "add files"
 * button (no `resetRef` needed). `accept` is the native filter.
 */
export function FileInput({
  id,
  label,
  description,
  error,
  required,
  className,
  placeholder,
  leftSection,
  clearable,
  disabled,
  multiple,
  value,
  onChange,
  ...props
}: FileInputProps) {
  const { t } = useTranslation();
  const field = useFieldControl({ id, description, error, required });
  const inputRef = useRef<HTMLInputElement>(null);

  const files = Array.isArray(value) ? value : value ? [value] : [];
  const names = files.map((file) => file.name).join(', ');

  const pick = (picked: File[]) => {
    if (multiple) (onChange as (files: File[]) => void)(picked);
    else (onChange as (file: File | null) => void)(picked[0] ?? null);
  };
  const clear = () => {
    pick([]);
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <InputWrapper field={field} label={label} description={description} error={error} required={required} className={className}>
      <div className="relative">
        <button
          type="button"
          disabled={disabled}
          aria-invalid={field.controlProps['aria-invalid']}
          aria-describedby={field.controlProps['aria-describedby']}
          className={cn(controlClass, 'flex cursor-pointer items-center gap-2 text-left', clearable && files.length > 0 && 'pr-7')}
          onClick={() => inputRef.current?.click()}
        >
          <span className="shrink-0 text-accent-text [&>svg]:size-4">{leftSection ?? <IconUpload />}</span>
          <span className={cn('min-w-0 flex-1 truncate', names ? 'text-text' : 'text-text-3')}>{names || placeholder || t('ui.chooseFiles')}</span>
        </button>
        {clearable && files.length > 0 && !disabled && (
          <button
            type="button"
            aria-label={t('ui.clear')}
            className="absolute top-1/2 right-1 grid size-5 -translate-y-1/2 place-items-center rounded-[2px] text-text-3 hover:bg-hover hover:text-text"
            onClick={clear}
          >
            <IconX className="size-3.5" />
          </button>
        )}
        <input
          {...props}
          ref={inputRef}
          id={field.id}
          type="file"
          multiple={multiple}
          disabled={disabled}
          tabIndex={-1}
          className="sr-only"
          onChange={(event) => {
            pick(Array.from(event.target.files ?? []));
            event.target.value = '';
          }}
        />
      </div>
    </InputWrapper>
  );
}
