import {
  IconArrowsDiagonal,
  IconArrowsDiagonalMinimize2,
  IconArrowUp,
  IconChevronDown,
  IconFileText,
  IconPlayerStopFilled,
  IconPlus,
  IconSparkles,
  IconTrash,
  IconX,
} from '@tabler/icons-react';
import { useEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth/useAuth';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { AssistantMessage } from './AssistantMessage';
import { MAX_MESSAGE_LENGTH } from './chat';
import { usePageContext } from './pageContext';
import { starterIcons, starterKind } from './starters';
import { useAssistantChat } from './useAssistantChat';

interface Props {
  open: boolean;
  expanded: boolean;
  onToggleExpanded: () => void;
  onClose: () => void;
}

const headerButtonClass = 'max-[62em]:size-11';

function Greeting() {
  const { t } = useTranslation('assistant');
  const hour = new Date().getHours();
  const part = hour >= 5 && hour < 12 ? 'morning' : hour >= 12 && hour < 18 ? 'day' : 'evening';
  return (
    <div className="flex flex-col gap-1">
      <IconSparkles className="mb-2 size-6 text-accent-text" aria-hidden />
      <h2 className="m-0 font-heading text-lg font-bold text-text">{t(`greeting.${part}`)}</h2>
      <p className="m-0 text-sm text-text-3">{t('greeting.subtitle')}</p>
    </div>
  );
}

/** Right-docked, non-modal "Ask AI" panel. It stays mounted while closed so an answer in progress is not lost. */
export function AssistantPanel({ open, expanded, onToggleExpanded, onClose }: Props) {
  const { t } = useTranslation('assistant');
  const { user } = useAuth();
  const page = usePageContext();
  const chat = useAssistantChat(user?.id ?? 0);
  const [draft, setDraft] = useState('');
  const [withContext, setWithContext] = useState(true);
  const [listOpen, setListOpen] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const wasOpen = useRef(open);

  const kind = starterKind(page);
  const lastMessage = chat.messages.at(-1);

  // Focus goes to the composer when the panel is opened (not when it was restored open on page load).
  useEffect(() => {
    if (open && !wasOpen.current) composerRef.current?.focus();
    wasOpen.current = open;
  }, [open]);

  useEffect(() => {
    const scroller = scrollRef.current;
    if (scroller && stickToBottom.current) scroller.scrollTop = scroller.scrollHeight;
  }, [chat.messages, open]);

  const submit = (text: string) => {
    if (!text.trim() || chat.streaming) return;
    stickToBottom.current = true;
    chat.send(text, withContext ? page : null);
    setDraft('');
    setWithContext(true);
  };

  const onComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit(draft);
    }
  };

  const onPanelKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    // Menus and popovers are portaled out of the panel, but their key events still bubble through React.
    if (event.key === 'Escape' && event.currentTarget.contains(event.target as Node)) onClose();
  };

  // Under 62em the panel covers the page, so following a link has to uncover it.
  const onPanelClick = (event: MouseEvent<HTMLElement>) => {
    if (window.matchMedia('(max-width: 62em)').matches && (event.target as Element).closest('a[href^="/"]')) onClose();
  };

  const contextLabel = page.entity
    ? t(`context.${page.entity.type}`, { id: page.entity.id })
    : t(`context.page.${page.section || 'home'}`, { defaultValue: page.path });

  return (
    <aside
      role="complementary"
      aria-label={t('title')}
      hidden={!open}
      onKeyDown={onPanelKeyDown}
      onClick={onPanelClick}
      className={cn(
        'fixed inset-0 z-50 flex flex-col bg-surface text-text',
        'min-[62em]:inset-auto min-[62em]:top-(--header-h) min-[62em]:right-0 min-[62em]:bottom-0 min-[62em]:z-30 min-[62em]:border-l min-[62em]:border-border min-[62em]:shadow-window',
        'animate-in duration-150 fade-in-0 motion-reduce:animate-none min-[62em]:slide-in-from-right-4',
        'min-[62em]:w-(--assistant-w)',
      )}
    >
      <div className="flex flex-none items-center gap-1 border-b border-border px-2 py-1.5">
        <Popover open={listOpen} onOpenChange={setListOpen}>
          <PopoverTrigger asChild>
            <Button variant="ghost" className="min-w-0 flex-1 justify-start px-2 max-[62em]:h-11" aria-label={t('conversations')}>
              <span className="truncate font-heading text-2xs font-bold tracking-wider uppercase">{chat.active?.title ?? t('newConversation')}</span>
              <IconChevronDown className="ml-auto" aria-hidden />
            </Button>
          </PopoverTrigger>
          <PopoverContent align="start" className="w-[min(320px,calc(100vw-2rem))] gap-0 p-1">
            <button
              type="button"
              className="flex h-7 w-full cursor-pointer items-center gap-2 rounded-sm px-2 text-left text-sm text-text-2 outline-none hover:bg-hover hover:text-text focus-visible:ring-1 focus-visible:ring-focus max-[62em]:h-11"
              onClick={() => {
                chat.startNew();
                setListOpen(false);
                composerRef.current?.focus();
              }}
            >
              <IconPlus className="size-4" aria-hidden />
              {t('newConversation')}
            </button>
            {chat.conversations.length > 0 && <div className="my-1 h-px bg-border" role="separator" />}
            <ul className="m-0 flex max-h-72 list-none flex-col overflow-y-auto p-0" aria-label={t('conversations')}>
              {chat.conversations.map((conversation) => (
                <li key={conversation.id} className="flex items-center gap-1">
                  <button
                    type="button"
                    aria-current={conversation.id === chat.active?.id || undefined}
                    className="h-7 min-w-0 flex-1 cursor-pointer truncate rounded-sm px-2 text-left text-sm text-text-2 outline-none hover:bg-hover hover:text-text focus-visible:ring-1 focus-visible:ring-focus aria-[current=true]:text-accent-text max-[62em]:h-11"
                    onClick={() => {
                      chat.select(conversation.id);
                      setListOpen(false);
                    }}
                  >
                    {conversation.title}
                  </button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="max-[62em]:size-11"
                    aria-label={t('deleteConversation', { title: conversation.title })}
                    onClick={() => chat.remove(conversation.id)}
                  >
                    <IconTrash />
                  </Button>
                </li>
              ))}
            </ul>
          </PopoverContent>
        </Popover>
        <Button variant="ghost" size="icon" className={headerButtonClass} aria-label={t('newConversation')} onClick={chat.startNew}>
          <IconPlus />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className={cn(headerButtonClass, 'max-[62em]:hidden')}
          aria-label={expanded ? t('collapse') : t('expand')}
          aria-pressed={expanded}
          onClick={onToggleExpanded}
        >
          {expanded ? <IconArrowsDiagonalMinimize2 /> : <IconArrowsDiagonal />}
        </Button>
        <Button variant="ghost" size="icon" className={headerButtonClass} aria-label={t('close')} onClick={onClose}>
          <IconX />
        </Button>
      </div>

      <div
        ref={scrollRef}
        onScroll={(event) => {
          const { scrollTop, scrollHeight, clientHeight } = event.currentTarget;
          stickToBottom.current = scrollHeight - scrollTop - clientHeight < 80;
        }}
        className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-4"
      >
        {chat.messages.length === 0 ? (
          <div className="flex flex-col gap-5 pt-4">
            <Greeting />
            <ul className="m-0 flex list-none flex-col gap-2 p-0" aria-label={t('startersLabel')}>
              {starterIcons[kind].map((StarterIcon, index) => {
                const title = t(`starters.${kind}.${index}.title`);
                return (
                  <li key={index}>
                    <button
                      type="button"
                      onClick={() => submit(title)}
                      className="flex w-full cursor-pointer items-start gap-3 rounded border border-border bg-surface p-3 text-left outline-none transition-colors duration-(--dur) hover:bg-hover focus-visible:ring-1 focus-visible:ring-focus"
                    >
                      <span className="grid size-8 flex-none place-items-center rounded bg-surface-sunken text-accent-text">
                        <StarterIcon className="size-4" aria-hidden />
                      </span>
                      <span className="flex min-w-0 flex-col gap-0.5">
                        <span className="text-sm font-semibold text-text">{title}</span>
                        <span className="text-xs text-text-3">{t(`starters.${kind}.${index}.subtitle`)}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : (
          chat.messages.map((message) => (
            <AssistantMessage
              key={message.id}
              message={message}
              streaming={chat.streaming && message === lastMessage}
              onRetry={message === lastMessage && !chat.streaming ? () => chat.retry(withContext ? page : null) : undefined}
            />
          ))
        )}
      </div>
      <p role="status" className="sr-only">
        {chat.announcement}
      </p>

      <div className="flex flex-none flex-col gap-1.5 border-t border-border p-3">
        <div className="flex flex-col rounded border border-border-strong bg-surface-sunken focus-within:border-focus focus-within:ring-1 focus-within:ring-focus">
          <Textarea
            ref={composerRef}
            value={draft}
            rows={1}
            maxLength={MAX_MESSAGE_LENGTH}
            aria-label={t('composer')}
            placeholder={t('placeholder')}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onComposerKeyDown}
            className="max-h-40 min-h-9 resize-none rounded-b-none border-0 bg-transparent px-2.5 py-2 ring-0 hover:border-0 focus-visible:border-0 focus-visible:ring-0"
          />
          <div className="flex items-center gap-2 px-1.5 pb-1.5">
            <div className="min-w-0 flex-1">
              {withContext && (
                <span
                  title={t('context.hint')}
                  className="inline-flex h-5 max-w-full items-center gap-1 rounded border border-border bg-surface pr-0.5 pl-1.5 text-2xs text-text-2"
                >
                  <IconFileText className="size-3 flex-none" aria-hidden />
                  <span className="truncate">{contextLabel}</span>
                  <button
                    type="button"
                    aria-label={t('context.remove')}
                    onClick={() => setWithContext(false)}
                    className="grid size-4 flex-none cursor-pointer place-items-center rounded-sm text-text-3 outline-none hover:bg-hover hover:text-text focus-visible:ring-1 focus-visible:ring-focus"
                  >
                    <IconX className="size-3" aria-hidden />
                  </button>
                </span>
              )}
            </div>
            {chat.streaming ? (
              <Button variant="secondary" size="icon" aria-label={t('stop')} onClick={chat.stop}>
                <IconPlayerStopFilled />
              </Button>
            ) : (
              <Button size="icon" aria-label={t('send')} disabled={!draft.trim()} onClick={() => submit(draft)}>
                <IconArrowUp />
              </Button>
            )}
          </div>
        </div>
        <p className="m-0 text-center text-2xs text-text-3">{t('disclaimer')}</p>
      </div>
    </aside>
  );
}
