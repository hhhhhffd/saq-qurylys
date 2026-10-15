import { useState, type ComponentProps } from 'react';
import { IconChevronDown, IconChevronUp } from '@tabler/icons-react';
import { InputWrapper } from '@/components/form/InputWrapper';
import { useFieldControl, type FieldProps } from '@/components/form/useFieldControl';
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group';

type NumberInputProps = FieldProps &
  Omit<ComponentProps<'input'>, keyof FieldProps | 'value' | 'onChange' | 'type' | 'min' | 'max' | 'step' | 'children'> & {
    /** a number; `''` when the field is empty; a string only while an unfinished number ("-", "1.") is typed */
    value: number | string;
    onChange: (value: number | string) => void;
    min?: number;
    max?: number;
    step?: number;
    allowDecimal?: boolean;
    allowNegative?: boolean;
    /** digits after the point; more are cut off while typing */
    decimalScale?: number;
    /** hide the +/- buttons (the arrow keys still step) */
    hideControls?: boolean;
  };

const toText = (value: number | string) => (value === '' ? '' : String(value));

/** Keeps what a number can be made of: digits, one point (a comma counts as a point), a leading minus. */
function sanitize(raw: string, allowDecimal: boolean, allowNegative: boolean, decimalScale?: number) {
  let text = raw.replace(',', '.').replace(allowDecimal ? /[^\d.-]/g : /[^\d-]/g, '');
  const negative = allowNegative && text.startsWith('-');
  text = text.replace(/-/g, '');
  const [integer, ...rest] = text.split('.');
  let fraction = rest.join('');
  if (decimalScale !== undefined) fraction = fraction.slice(0, decimalScale);
  const hasPoint = allowDecimal && (rest.length > 0 || text.endsWith('.')) && decimalScale !== 0;
  return `${negative ? '-' : ''}${integer}${hasPoint ? '.' : ''}${fraction}`;
}

const isComplete = (text: string) => /^-?\d*\.?\d+$/.test(text);

function clamp(value: number, min?: number, max?: number) {
  return Math.min(Math.max(value, min ?? -Infinity), max ?? Infinity);
}

/** Numeric field (replaces the Mantine `NumberInput`): +/- buttons, arrow keys, clamping to `min`/`max` on blur. */
export function NumberInput({
  id,
  label,
  description,
  error,
  required,
  className,
  value,
  onChange,
  min,
  max,
  step = 1,
  allowDecimal = true,
  allowNegative = true,
  decimalScale,
  hideControls = false,
  disabled,
  onBlur,
  ...props
}: NumberInputProps) {
  const field = useFieldControl({ id, description, error, required });
  // The text is what the user typed; it follows `value` only when the parent changes it to something else.
  const [text, setText] = useState(toText(value));
  const [syncedValue, setSyncedValue] = useState(value);
  if (value !== syncedValue) {
    setSyncedValue(value);
    if (toText(value) !== text && !(isComplete(text) && Number(text) === value)) setText(toText(value));
  }

  const commit = (next: string) => {
    setText(next);
    if (next === '') onChange('');
    else if (isComplete(next)) onChange(Number(next));
    else onChange(next);
  };

  const stepBy = (direction: 1 | -1) => {
    const base = isComplete(text) ? Number(text) : 0;
    // Rounding to the step's own decimals keeps 0.1 + 0.2 from becoming 0.30000000000000004.
    const decimals = (String(step).split('.')[1] ?? '').length;
    const next = clamp(Number((base + direction * step).toFixed(decimals)), min, max);
    commit(String(next));
  };

  return (
    <InputWrapper field={field} label={label} description={description} error={error} required={required} className={className}>
      <InputGroup>
        <InputGroupInput
          {...field.controlProps}
          {...props}
          type="text"
          inputMode={allowDecimal ? 'decimal' : 'numeric'}
          disabled={disabled}
          value={text}
          onChange={(event) => commit(sanitize(event.target.value, allowDecimal, allowNegative, decimalScale))}
          onKeyDown={(event) => {
            if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
              event.preventDefault();
              stepBy(event.key === 'ArrowUp' ? 1 : -1);
            }
            props.onKeyDown?.(event);
          }}
          onBlur={(event) => {
            if (isComplete(text)) commit(String(clamp(Number(text), min, max)));
            else if (text !== '') commit('');
            onBlur?.(event);
          }}
        />
        {!hideControls && (
          <InputGroupAddon align="inline-end" className="gap-0">
            <div className="flex h-full flex-col justify-center">
              <button
                type="button"
                tabIndex={-1}
                disabled={disabled}
                aria-hidden
                className="grid h-3 w-5 place-items-center text-accent-text hover:text-text disabled:opacity-50"
                onClick={() => stepBy(1)}
              >
                <IconChevronUp className="size-3" />
              </button>
              <button
                type="button"
                tabIndex={-1}
                disabled={disabled}
                aria-hidden
                className="grid h-3 w-5 place-items-center text-accent-text hover:text-text disabled:opacity-50"
                onClick={() => stepBy(-1)}
              >
                <IconChevronDown className="size-3" />
              </button>
            </div>
          </InputGroupAddon>
        )}
      </InputGroup>
    </InputWrapper>
  );
}
