import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { useNavigate } from 'react-router';
import { IconSearch } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { SEARCH_MIN_LENGTH, useGlobalSearch } from '@/api/hooks/search';
import { ZoneBadge } from '@/components/Zone';
import { InputGroup, InputGroupAddon, InputGroupInput } from '@/components/ui/input-group';
import { useEnum } from '@/i18n/useEnum';
import { useDebouncedValue } from '@/lib/hooks';
import { cn } from '@/lib/utils';

interface Item {
  key: string;
  to: string;
  node: ReactNode;
}

const rowClass =
  'flex w-full min-h-11 cursor-pointer flex-col justify-center gap-0.5 rounded px-3 py-1.5 text-left text-base text-text outline-none aria-selected:bg-surface-sunken aria-selected:ring-1 aria-selected:ring-focus';

function isTypingTarget(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
}

/** Header search: objects, developers and signal cards in one box. Enter opens the first hit, "/" focuses the box. */
export function GlobalSearch() {
  const { t } = useTranslation();
  const e = useEnum();
  const navigate = useNavigate();
  const listId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [query] = useDebouncedValue(text.trim(), 300);
  const search = useGlobalSearch(query);
  const data = search.data;

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key !== '/' || event.ctrlKey || event.metaKey || event.altKey || isTypingTarget(event.target)) return;
      event.preventDefault();
      inputRef.current?.focus();
    };
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('pointerdown', onPointerDown);
    };
  }, []);

  const groups = useMemo(() => {
    if (!data) return [];
    const matched = (field: string) => t('globalSearch.matchedBy', { field: t(`globalSearch.fields.${field}`, { defaultValue: field }) });
    return [
      {
        id: 'objects',
        title: t('globalSearch.objects'),
        items: data.objects.map<Item>((hit) => ({
          key: `object-${hit.id}`,
          to: `/objects/${hit.id}`,
          node: (
            <>
              <span className="flex items-center justify-between gap-2">
                <span className="min-w-0 truncate font-medium">{hit.name}</span>
                <ZoneBadge zone={hit.zone} />
              </span>
              <span className="truncate text-sm text-text-3">
                {[hit.address, hit.developer_name, hit.code].filter(Boolean).join(' · ')}
              </span>
              <span className="text-xs text-text-3">{matched(hit.match)}</span>
            </>
          ),
        })),
      },
      {
        id: 'developers',
        title: t('globalSearch.developers'),
        items: data.developers.map<Item>((hit) => ({
          key: `developer-${hit.id}`,
          to: hit.object_id == null ? '' : `/objects/${hit.object_id}`,
          node: (
            <>
              <span className="truncate font-medium">{hit.name}</span>
              <span className="text-sm text-text-3">
                {hit.bin}
                {hit.object_id == null && ` · ${t('globalSearch.noObjects')}`}
              </span>
            </>
          ),
        })),
      },
      {
        id: 'signals',
        title: t('globalSearch.signals'),
        items: data.signals.map<Item>((hit) => ({
          key: `signal-${hit.id}`,
          to: `/signals/${hit.id}`,
          node: (
            <>
              <span className="truncate font-medium tabular-nums">{hit.number}</span>
              <span className="truncate text-sm text-text-3">
                {hit.object_name} · {e('signal_status', hit.status)}
              </span>
            </>
          ),
        })),
      },
    ].filter((group) => group.items.length > 0);
  }, [data, t, e]);

  const typed = text.trim();
  const showPanel = open && typed.length > 0;

  let status: string | null = null;
  if (typed.length < SEARCH_MIN_LENGTH) status = t('globalSearch.minLength');
  else if (search.isError) status = t('globalSearch.error');
  else if (!data || query !== typed || search.isPlaceholderData) status = t('globalSearch.loading');
  else if (groups.length === 0) status = t('globalSearch.nothingFound');

  // Hits without a target (a developer with no object in scope) are shown but cannot be chosen. While a status is
  // shown the previous query's hits are hidden, so Enter and the arrows must not reach them either.
  const selectable = status ? [] : groups.flatMap((group) => group.items).filter((item) => item.to !== '');
  const activeKey = selectable[Math.min(active, selectable.length - 1)]?.key;

  const choose = (item: Item) => {
    setOpen(false);
    setText('');
    if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
    void navigate(item.to);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      setOpen(false);
      return;
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      setOpen(true);
      if (selectable.length === 0) return;
      const step = event.key === 'ArrowDown' ? 1 : -1;
      const current = Math.min(active, selectable.length - 1);
      setActive((current + step + selectable.length) % selectable.length);
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      const item = selectable[Math.min(active, selectable.length - 1)];
      if (item) choose(item);
    }
  };

  return (
    <div
      ref={rootRef}
      className="relative order-last basis-full pb-2"
    >
      <InputGroup className="h-10 text-base">
        <InputGroupAddon>
          <IconSearch aria-hidden className="size-5" />
        </InputGroupAddon>
        <InputGroupInput
          ref={inputRef}
          type="search"
          role="combobox"
          aria-label={t('globalSearch.label')}
          aria-expanded={showPanel}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={showPanel && activeKey ? `${listId}-${activeKey}` : undefined}
          autoComplete="off"
          maxLength={200}
          placeholder={t('globalSearch.placeholder')}
          className="px-2 text-base"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setActive(0);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
        />
      </InputGroup>
      {showPanel && (
        <div
          id={listId}
          role="listbox"
          aria-label={t('globalSearch.label')}
          className="absolute top-full left-0 z-50 mt-1 max-h-[70vh] w-[max(100%,28rem)] max-w-[calc(100vw-2*var(--gutter))] overflow-y-auto rounded border border-border-strong bg-popover p-1 shadow-2 max-[62em]:w-full"
        >
          {status && (
            <div role="status" className="px-3 py-3 text-base text-text-3">
              {status}
            </div>
          )}
          {!status &&
            groups.map((group) => (
              <div key={group.id} role="group" aria-label={group.title}>
                <div className="px-3 pt-2 pb-1 font-heading text-xs font-semibold tracking-wider text-text-3 uppercase">
                  {group.title}
                </div>
                {group.items.map((item) => {
                  const id = `${listId}-${item.key}`;
                  if (item.to === '') {
                    return (
                      <div key={item.key} role="option" aria-selected={false} aria-disabled id={id} className={cn(rowClass, 'cursor-default opacity-70')}>
                        {item.node}
                      </div>
                    );
                  }
                  return (
                    <div
                      key={item.key}
                      id={id}
                      role="option"
                      aria-selected={item.key === activeKey}
                      className={rowClass}
                      onPointerEnter={() => setActive(selectable.findIndex((s) => s.key === item.key))}
                      onPointerDown={(event) => event.preventDefault()}
                      onClick={() => choose(item)}
                    >
                      {item.node}
                    </div>
                  );
                })}
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
