import * as React from 'react';
import { IconCheck, IconChevronDown, IconX } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { InputGroup } from '@/components/ui/input-group';
import { Popover, PopoverAnchor, PopoverContent } from '@/components/ui/popover';
import { Spinner } from '@/components/ui/spinner';
import { itemClass } from '@/components/ui/styles';
import { cn } from '@/lib/utils';

export interface ComboboxOption {
  value: string;
  label: string;
  disabled?: boolean;
}

interface BaseProps {
  options: ComboboxOption[];
  /** shown while nothing is chosen */
  placeholder?: string;
  /** replaces the "nothing found" text */
  emptyText?: React.ReactNode;
  /**
   * Server-side search: called with the typed text (debounce it with `useDebouncedValue`) and with `''` when the list
   * closes. Passing it turns the local filtering off, so `options` is shown as given.
   */
  onSearchChange?: (text: string) => void;
  loading?: boolean;
  clearable?: boolean;
  disabled?: boolean;
  id?: string;
  name?: string;
  className?: string;
  'aria-invalid'?: boolean;
  'aria-label'?: string;
  'aria-labelledby'?: string;
  'aria-describedby'?: string;
  'aria-required'?: boolean;
}

interface BaseInternalProps extends BaseProps {
  multiple: boolean;
  selected: string[];
  onToggle: (value: string) => void;
  onClear: () => void;
  /** multi only: the Backspace key in an empty field takes the last chip off */
  onRemoveLast: () => void;
}

/**
 * Editable combobox on the ARIA 1.2 pattern: the text field is the `combobox` (it shows the chosen label, typing
 * filters), the list is a `listbox` of `option`s in a popover. Focus never leaves the field.
 */
function ComboboxBase({
  options,
  placeholder,
  emptyText,
  onSearchChange,
  loading,
  clearable,
  disabled,
  className,
  multiple,
  selected,
  onToggle,
  onClear,
  onRemoveLast,
  ...aria
}: BaseInternalProps) {
  const { t } = useTranslation();
  const listboxId = React.useId();
  const anchorRef = React.useRef<HTMLDivElement>(null);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const [open, setOpen] = React.useState(false);
  // null: the user is not typing, the field shows the chosen label
  const [query, setQuery] = React.useState<string | null>(null);
  const [active, setActive] = React.useState(0);

  const labelOf = (value: string) => options.find((option) => option.value === value)?.label ?? value;
  const hasValue = selected.length > 0;
  const needle = query?.trim().toLowerCase() ?? '';
  const shown = onSearchChange || !needle ? options : options.filter((option) => option.label.toLowerCase().includes(needle));
  const activeIndex = Math.min(active, shown.length - 1);
  const optionId = (index: number) => `${listboxId}-${index}`;

  React.useEffect(() => {
    if (open) document.getElementById(optionId(activeIndex))?.scrollIntoView({ block: 'nearest' });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- optionId depends only on listboxId
  }, [open, activeIndex, listboxId]);

  const openList = () => {
    if (open || disabled) return;
    const selectedIndex = multiple ? -1 : options.findIndex((option) => option.value === selected[0]);
    setActive(Math.max(selectedIndex, 0));
    setOpen(true);
  };

  const closeList = () => {
    setOpen(false);
    if (query !== null) onSearchChange?.('');
    setQuery(null);
  };

  const choose = (option: ComboboxOption) => {
    if (option.disabled) return;
    onToggle(option.value);
    if (!multiple) {
      closeList();
      return;
    }
    // multi: the list stays open for the next pick
    if (query !== null) onSearchChange?.('');
    setQuery(null);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) {
        openList();
        return;
      }
      const step = event.key === 'ArrowDown' ? 1 : -1;
      setActive(Math.min(Math.max(activeIndex + step, 0), shown.length - 1));
    } else if (event.key === 'Enter' && open) {
      // never submit the surrounding form from an open list
      event.preventDefault();
      const option = shown[activeIndex];
      if (option) choose(option);
    } else if (event.key === 'Backspace' && multiple && !query && hasValue) {
      onRemoveLast();
    }
  };

  const inputValue = query ?? (multiple || !hasValue ? '' : labelOf(selected[0]));

  return (
    <Popover
      open={open && !disabled}
      onOpenChange={(next) => {
        if (!next) closeList();
      }}
    >
      <PopoverAnchor asChild>
        <InputGroup
          ref={anchorRef}
          data-slot="combobox"
          className={cn('h-auto min-h-7 flex-wrap gap-1 py-px pr-1 pl-0 has-[input:disabled]:opacity-50', className)}
          onClick={() => inputRef.current?.focus()}
        >
          {multiple &&
            selected.map((value) => (
              <span key={value} className="ml-1 inline-flex h-5 max-w-full items-center gap-1 rounded-sm border border-border-strong bg-hover pr-0.5 pl-1.5 text-2xs text-text">
                <span className="truncate">{labelOf(value)}</span>
                <button
                  type="button"
                  tabIndex={-1}
                  disabled={disabled}
                  aria-label={t('ui.remove', { value: labelOf(value) })}
                  className="grid size-3.5 place-items-center rounded-[2px] text-text-3 hover:bg-pressed hover:text-text"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => onToggle(value)}
                >
                  <IconX className="size-2.5" />
                </button>
              </span>
            ))}
          <input
            ref={inputRef}
            data-slot="input-group-control"
            type="text"
            role="combobox"
            aria-expanded={open}
            aria-haspopup="listbox"
            aria-controls={open ? listboxId : undefined}
            aria-activedescendant={open && shown.length > 0 ? optionId(activeIndex) : undefined}
            aria-autocomplete="list"
            autoComplete="off"
            disabled={disabled}
            placeholder={hasValue && multiple ? undefined : placeholder}
            value={inputValue}
            className={cn(
              'h-6 min-w-16 flex-1 border-0 bg-transparent pl-2 text-sm text-text-2 outline-none placeholder:text-text-3 focus-visible:text-text disabled:cursor-not-allowed',
              !multiple && hasValue && query === null && 'text-text',
            )}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
              onSearchChange?.(event.target.value);
              if (!open) setOpen(true);
            }}
            onClick={openList}
            onKeyDown={onKeyDown}
            onBlur={closeList}
            {...aria}
          />
          {loading && <Spinner className="size-3.5 text-text-3" />}
          {clearable && hasValue && !disabled && (
            <button
              type="button"
              tabIndex={-1}
              aria-label={t('ui.clear')}
              className="grid size-5 shrink-0 place-items-center rounded-[2px] text-text-3 hover:bg-hover hover:text-text"
              onMouseDown={(event) => event.preventDefault()}
              onClick={onClear}
            >
              <IconX className="size-3.5" />
            </button>
          )}
          <button
            type="button"
            tabIndex={-1}
            aria-hidden
            disabled={disabled}
            className="grid size-5 shrink-0 place-items-center rounded-[2px] text-accent-text"
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => (open ? closeList() : openList())}
          >
            <IconChevronDown className="size-3.5" />
          </button>
        </InputGroup>
      </PopoverAnchor>
      <PopoverContent
        align="start"
        className="w-(--radix-popover-trigger-width) min-w-40 gap-0 p-1"
        // Focus stays in the field: neither opening nor pressing on the list moves it.
        onOpenAutoFocus={(event) => event.preventDefault()}
        onCloseAutoFocus={(event) => event.preventDefault()}
        onMouseDown={(event) => event.preventDefault()}
        // Pressing the field itself is not "outside": it has its own handlers.
        onInteractOutside={(event) => {
          if (anchorRef.current?.contains(event.target as Node)) event.preventDefault();
        }}
        // A surrounding dialog locks wheel scrolling outside its own DOM; the list is portaled out of it.
        onWheel={(event) => event.stopPropagation()}
      >
        <div id={listboxId} role="listbox" aria-multiselectable={multiple || undefined} className="max-h-64 overflow-y-auto">
          {shown.length === 0 && (
            <div className="py-3 text-center text-xs text-text-3">{loading ? t('loading') : (emptyText ?? t('ui.nothingFound'))}</div>
          )}
          {shown.map((option, index) => {
            const isSelected = selected.includes(option.value);
            return (
              <div
                key={option.value}
                id={optionId(index)}
                role="option"
                aria-selected={isSelected}
                aria-disabled={option.disabled || undefined}
                data-selected={index === activeIndex || undefined}
                data-disabled={option.disabled || undefined}
                className={cn(itemClass, isSelected && 'text-text')}
                onMouseMove={() => setActive(index)}
                onClick={() => choose(option)}
              >
                <span className="min-w-0 flex-1 truncate">{option.label}</span>
                {isSelected && <IconCheck className="size-3.5 text-accent-text" />}
              </div>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}

interface ComboboxProps extends BaseProps {
  value: string | null;
  onChange: (value: string | null) => void;
}

/** Searchable single select. For a short list without search use `Select` (ui/select). */
function Combobox({ value, onChange, ...props }: ComboboxProps) {
  return (
    <ComboboxBase
      {...props}
      multiple={false}
      selected={value === null ? [] : [value]}
      onToggle={(next) => onChange(next)}
      onClear={() => onChange(null)}
      onRemoveLast={() => undefined}
    />
  );
}

interface MultiComboboxProps extends BaseProps {
  value: string[];
  onChange: (value: string[]) => void;
}

/** Searchable multi select: the list stays open while picking, chosen options are removable chips. */
function MultiCombobox({ value, onChange, ...props }: MultiComboboxProps) {
  return (
    <ComboboxBase
      {...props}
      multiple
      selected={value}
      onToggle={(next) => onChange(value.includes(next) ? value.filter((item) => item !== next) : [...value, next])}
      onClear={() => onChange([])}
      onRemoveLast={() => onChange(value.slice(0, -1))}
    />
  );
}

export { Combobox, MultiCombobox };
