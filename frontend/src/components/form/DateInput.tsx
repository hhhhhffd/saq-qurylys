import { useState } from 'react';
import { IconCalendar, IconX } from '@tabler/icons-react';
import { isSameDay } from 'date-fns';
import { useTranslation } from 'react-i18next';
import { calendarLocale, formatApiDate, formatDisplayDate, parseApiDate, parseTypedDate } from '@/components/form/dates';
import { InputWrapper } from '@/components/form/InputWrapper';
import { useFieldControl, type FieldProps } from '@/components/form/useFieldControl';
import { Calendar } from '@/components/ui/calendar';
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group';
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

interface DateInputProps extends FieldProps {
  /** `YYYY-MM-DD` (what the API uses; no time zone shifts) or null */
  value: string | null;
  onChange: (value: string | null) => void;
  placeholder?: string;
  /** a button that empties the field (typing an empty text empties it anyway) */
  clearable?: boolean;
  /** `YYYY-MM-DD` bounds */
  minDate?: string;
  maxDate?: string;
  disabled?: boolean;
  name?: string;
  onBlur?: () => void;
}

/**
 * Date field: type `DD.MM.YYYY` (or `YYYY-MM-DD`) or pick from the calendar popover (replaces the Mantine `DateInput`).
 * A valid text is committed at once; leaving the field with an unfinished or impossible date restores the last value.
 */
export function DateInput({
  id,
  label,
  description,
  error,
  required,
  className,
  value,
  onChange,
  placeholder,
  clearable,
  minDate,
  maxDate,
  disabled,
  name,
  onBlur,
}: DateInputProps) {
  const { t, i18n } = useTranslation();
  const field = useFieldControl({ id, description, error, required });
  const [open, setOpen] = useState(false);
  const date = parseApiDate(value);
  const min = parseApiDate(minDate);
  const max = parseApiDate(maxDate);

  // The text follows `value` only when the parent changes it to a different day than the text says.
  const [text, setText] = useState(formatDisplayDate(date));
  const [syncedValue, setSyncedValue] = useState(value);
  if (value !== syncedValue) {
    setSyncedValue(value);
    const typed = parseTypedDate(text);
    if (!(typed && date && isSameDay(typed, date)) && !(date === null && text === '')) setText(formatDisplayDate(date));
  }

  const inRange = (candidate: Date) => (!min || candidate >= min) && (!max || candidate <= max);

  return (
    <InputWrapper field={field} label={label} description={description} error={error} required={required} className={className}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverAnchor asChild>
          <InputGroup>
            <InputGroupInput
              {...field.controlProps}
              name={name}
              inputMode="numeric"
              autoComplete="off"
              disabled={disabled}
              placeholder={placeholder ?? t('ui.datePlaceholder')}
              value={text}
              onChange={(event) => {
                const next = event.target.value;
                setText(next);
                if (next.trim() === '') {
                  onChange(null);
                  return;
                }
                const typed = parseTypedDate(next);
                if (typed && inRange(typed)) onChange(formatApiDate(typed));
              }}
              onBlur={() => {
                setText(formatDisplayDate(date));
                onBlur?.();
              }}
            />
            <InputGroupAddon align="inline-end">
              {clearable && date && !disabled && (
                <InputGroupButton aria-label={t('ui.clear')} onClick={() => onChange(null)}>
                  <IconX />
                </InputGroupButton>
              )}
              <PopoverTrigger asChild>
                <InputGroupButton aria-label={t('ui.chooseDate')} disabled={disabled}>
                  <IconCalendar />
                </InputGroupButton>
              </PopoverTrigger>
            </InputGroupAddon>
          </InputGroup>
        </PopoverAnchor>
        <PopoverContent align="start" className="w-auto p-0">
          <Calendar
            mode="single"
            required
            autoFocus
            selected={date ?? undefined}
            defaultMonth={date ?? undefined}
            onSelect={(next) => {
              onChange(formatApiDate(next));
              setOpen(false);
            }}
            locale={calendarLocale(i18n.language)}
            weekStartsOn={1}
            captionLayout="dropdown"
            startMonth={new Date(2000, 0)}
            endMonth={new Date(2100, 11)}
            disabled={[...(min ? [{ before: min }] : []), ...(max ? [{ after: max }] : [])]}
          />
        </PopoverContent>
      </Popover>
    </InputWrapper>
  );
}
