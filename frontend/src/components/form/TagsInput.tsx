import { useRef, useState, type ComponentProps } from 'react';
import { IconX } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { InputWrapper } from '@/components/form/InputWrapper';
import { useFieldControl, type FieldProps } from '@/components/form/useFieldControl';
import { InputGroup } from '@/components/ui/input-group';

type TagsInputProps = FieldProps &
  Omit<ComponentProps<'input'>, keyof FieldProps | 'value' | 'onChange' | 'type' | 'children'> & {
    value: string[];
    onChange: (value: string[]) => void;
    /** typing one of these cuts a tag (default `[',']`); Enter and leaving the field do it too */
    splitChars?: string[];
    maxTags?: number;
  };

/** Free-text tags as chips (replaces the Mantine `TagsInput`). Duplicates are ignored, Backspace removes the last tag. */
export function TagsInput({
  id,
  label,
  description,
  error,
  required,
  className,
  value,
  onChange,
  splitChars = [','],
  maxTags,
  disabled,
  placeholder,
  onBlur,
  onKeyDown,
  ...props
}: TagsInputProps) {
  const { t } = useTranslation();
  const field = useFieldControl({ id, description, error, required });
  const inputRef = useRef<HTMLInputElement>(null);
  const [text, setText] = useState('');

  const add = (candidates: string[]) => {
    const fresh = candidates.map((tag) => tag.trim()).filter((tag, index, all) => tag !== '' && !value.includes(tag) && all.indexOf(tag) === index);
    const room = maxTags === undefined ? fresh : fresh.slice(0, Math.max(maxTags - value.length, 0));
    if (room.length > 0) onChange([...value, ...room]);
  };

  const splitPattern = new RegExp(`[${splitChars.map((char) => char.replace(/[\\\]^-]/g, '\\$&')).join('')}]`);

  return (
    <InputWrapper field={field} label={label} description={description} error={error} required={required} className={className}>
      <InputGroup className="h-auto min-h-7 flex-wrap gap-1 py-px pl-0 has-[input:disabled]:opacity-50" onClick={() => inputRef.current?.focus()}>
        {value.map((tag) => (
          <span key={tag} className="ml-1 inline-flex h-5 max-w-full items-center gap-1 rounded-sm border border-border-strong bg-hover pr-0.5 pl-1.5 text-2xs text-text">
            <span className="truncate">{tag}</span>
            <button
              type="button"
              tabIndex={-1}
              disabled={disabled}
              aria-label={t('ui.remove', { value: tag })}
              className="grid size-3.5 place-items-center rounded-[2px] text-text-3 hover:bg-pressed hover:text-text"
              onClick={() => onChange(value.filter((item) => item !== tag))}
            >
              <IconX className="size-2.5" />
            </button>
          </span>
        ))}
        <input
          {...field.controlProps}
          {...props}
          ref={inputRef}
          data-slot="input-group-control"
          type="text"
          disabled={disabled}
          placeholder={value.length > 0 ? undefined : placeholder}
          value={text}
          className="h-6 min-w-24 flex-1 border-0 bg-transparent pl-2 text-sm text-text-2 outline-none placeholder:text-text-3 focus-visible:text-text disabled:cursor-not-allowed"
          onChange={(event) => {
            const parts = event.target.value.split(splitPattern);
            if (parts.length === 1) {
              setText(event.target.value);
              return;
            }
            const rest = parts.pop() ?? '';
            add(parts);
            setText(rest);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && text.trim() !== '') {
              event.preventDefault();
              add([text]);
              setText('');
            } else if (event.key === 'Backspace' && text === '' && value.length > 0) {
              onChange(value.slice(0, -1));
            }
            onKeyDown?.(event);
          }}
          onBlur={(event) => {
            add([text]);
            setText('');
            onBlur?.(event);
          }}
        />
      </InputGroup>
    </InputWrapper>
  );
}
