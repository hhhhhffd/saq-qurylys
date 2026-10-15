import { useState } from 'react';
import { IconCalendarTime, IconX } from '@tabler/icons-react';
import { format, isEqual, set } from 'date-fns';
import { useTranslation } from 'react-i18next';
import { calendarLocale, formatApiDateTime, formatDisplayDateTime, parseApiDateTime, parseTypedDateTime } from '@/components/form/dates';
import { InputWrapper } from '@/components/form/InputWrapper';
import { useFieldControl, type FieldProps } from '@/components/form/useFieldControl';
import { Calendar } from '@/components/ui/calendar';
import { InputGroup, InputGroupAddon, InputGroupButton, InputGroupInput } from '@/components/ui/input-group';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverAnchor, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

interface DateTimeInputProps extends FieldProps {
  /** `YYYY-MM-DD HH:mm:ss` in local time, no zone (what the Mantine picker produced), or null */
  value: string | null;
  onChange: (value: string | null) => void;
  placeholder?: string;
  clearable?: boolean;
  disabled?: boolean;
  name?: string;
  onBlur?: () => void;
}

/**
 * Date and time: type `DD.MM.YYYY HH:mm` or pick the day in the popover and the time under it (replaces the Mantine
 * `DateTimePicker`). The value is local time without a zone; convert with `new Date(value).toISOString()` for the API.
 */
export function DateTimeInput({
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
  disabled,
  name,
  onBlur,
}: DateTimeInputProps) {
  const { t, i18n } = useTranslation();
  const field = useFieldControl({ id, description, error, required });
  const [open, setOpen] = useState(false);
  const date = parseApiDateTime(value);

  const [text, setText] = useState(formatDisplayDateTime(date));
  const [syncedValue, setSyncedValue] = useState(value);
  if (value !== syncedValue) {
    setSyncedValue(value);
    const typed = parseTypedDateTime(text);
    if (!(typed && date && isEqual(typed, date)) && !(date === null && text === '')) setText(formatDisplayDateTime(date));
  }

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
              placeholder={placeholder ?? t('ui.dateTimePlaceholder')}
              value={text}
              onChange={(event) => {
                const next = event.target.value;
                setText(next);
                if (next.trim() === '') {
                  onChange(null);
                  return;
                }
                const typed = parseTypedDateTime(next);
                if (typed) onChange(formatApiDateTime(typed));
              }}
              onBlur={() => {
                setText(formatDisplayDateTime(date));
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
                <InputGroupButton aria-label={t('ui.chooseDateTime')} disabled={disabled}>
                  <IconCalendarTime />
                </InputGroupButton>
              </PopoverTrigger>
            </InputGroupAddon>
          </InputGroup>
        </PopoverAnchor>
        <PopoverContent align="start" className="w-auto gap-0 p-0">
          <Calendar
            mode="single"
            required
            autoFocus
            selected={date ?? undefined}
            defaultMonth={date ?? undefined}
            onSelect={(next) => onChange(formatApiDateTime(set(next, { hours: date?.getHours() ?? 0, minutes: date?.getMinutes() ?? 0, seconds: 0 })))}
            locale={calendarLocale(i18n.language)}
            weekStartsOn={1}
            captionLayout="dropdown"
            startMonth={new Date(2000, 0)}
            endMonth={new Date(2100, 11)}
          />
          <div className="flex items-center gap-2 border-t border-border px-3 py-2">
            <Label htmlFor={`${field.id}-time`}>{t('ui.time')}</Label>
            <Input
              id={`${field.id}-time`}
              type="time"
              className="w-24 scheme-dark"
              disabled={!date}
              value={date ? format(date, 'HH:mm') : ''}
              onChange={(event) => {
                const [hours, minutes] = event.target.value.split(':').map(Number);
                if (date && Number.isFinite(hours) && Number.isFinite(minutes)) {
                  onChange(formatApiDateTime(set(date, { hours, minutes, seconds: 0 })));
                }
              }}
            />
          </div>
        </PopoverContent>
      </Popover>
    </InputWrapper>
  );
}
