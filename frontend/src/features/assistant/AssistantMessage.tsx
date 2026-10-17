import { IconAlertTriangle, IconChevronRight, IconPlayerStop } from '@tabler/icons-react';
import { memo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';
import { cn } from '@/lib/utils';
import { AssistantMarkdown } from './AssistantMarkdown';
import type { ChatMessage } from './chat';

interface Props {
  message: ChatMessage;
  /** the answer is still being written */
  streaming: boolean;
  /** only the last answer can be asked again */
  onRetry?: () => void;
}

function Sources({ sources }: { sources: NonNullable<ChatMessage['sources']> }) {
  const { t } = useTranslation('assistant');
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex cursor-pointer items-center gap-1 rounded text-xs text-text-3 outline-none hover:text-text-2 focus-visible:ring-1 focus-visible:ring-focus"
      >
        <IconChevronRight className={cn('size-3.5 transition-transform duration-(--dur)', open && 'rotate-90')} aria-hidden />
        {t('sources', { count: sources.length })}
      </button>
      {open && (
        <ul className="m-0 mt-1 flex list-none flex-col gap-0.5 p-0 pl-4 text-xs">
          {sources.map((source) => (
            <li key={source.id}>
              {source.page ? (
                <Link to={source.page} className="text-link underline underline-offset-2 hover:text-accent-text">
                  {source.title}
                </Link>
              ) : (
                <span className="text-text-2">{source.title}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export const AssistantMessage = memo(function AssistantMessage({ message, streaming, onRetry }: Props) {
  const { t } = useTranslation('assistant');

  if (message.role === 'user') {
    return (
      <div className="ml-auto max-w-[85%] rounded border border-border-strong bg-surface-sunken px-3 py-2 text-sm break-words whitespace-pre-wrap text-text">
        {message.content}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5 text-sm break-words text-text-2">
      {message.tools?.map((tool, index) => (
        <p key={index} className="m-0 flex items-center gap-1.5 text-xs text-text-3">
          {tool.done ? <span className="size-1 shrink-0 rounded-full bg-text-disabled" aria-hidden /> : <Spinner className="size-3" aria-label={t('status.working')} />}
          {tool.label}
        </p>
      ))}
      {message.content ? (
        <div>
          <AssistantMarkdown>{message.content}</AssistantMarkdown>
        </div>
      ) : (
        streaming && !message.tools?.length && <Spinner className="size-3.5 text-text-3" aria-label={t('status.thinking')} />
      )}
      {message.status === 'stopped' && (
        <p className="m-0 flex items-center gap-1 text-xs text-text-3">
          <IconPlayerStop className="size-3.5" aria-hidden />
          {t('stopped')}
        </p>
      )}
      {message.status === 'error' && (
        <div role="alert" className="flex flex-wrap items-center gap-2 rounded border border-zone-red/50 bg-zone-red-bg px-2.5 py-2 text-xs text-text">
          <IconAlertTriangle className="size-3.5 shrink-0 text-zone-red" aria-hidden />
          <span className="min-w-0 flex-1">{t(`errors.${message.errorCode}`, { defaultValue: t('errors.generic') })}</span>
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              {t('retry')}
            </Button>
          )}
        </div>
      )}
      {message.sources && message.sources.length > 0 && <Sources sources={message.sources} />}
    </div>
  );
});
