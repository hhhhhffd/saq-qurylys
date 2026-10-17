import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiStream, ApiError } from '@/api/client';
import {
  type AssistantEvent,
  type ChatMessage,
  type Conversation,
  loadConversations,
  MAX_API_MESSAGES,
  MAX_CONVERSATIONS,
  MAX_MESSAGE_LENGTH,
  readEvents,
  saveConversations,
  titleFrom,
} from './chat';
import type { PageContext } from './pageContext';

const newId = () => crypto.randomUUID();

/** Conversations of one user, the active one and the streaming of its answer. `null` active id is an empty new dialog. */
export function useAssistantChat(userId: number) {
  const { t, i18n } = useTranslation('assistant');
  const [conversations, setConversations] = useState(() => loadConversations(userId));
  const [activeId, setActiveId] = useState<string | null>(() => conversations[0]?.id ?? null);
  const [streaming, setStreaming] = useState(false);
  /** short status for the screen reader; changes per stage, not per token */
  const [announcement, setAnnouncement] = useState('');
  const controllerRef = useRef<AbortController | null>(null);

  const active = conversations.find((conversation) => conversation.id === activeId) ?? null;
  const messages = active?.messages ?? [];

  // Saved when a stream ends, not on every token.
  useEffect(() => {
    if (!streaming) saveConversations(userId, conversations);
  }, [userId, conversations, streaming]);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const stop = useCallback(() => controllerRef.current?.abort(), []);

  /** Streams the answer to `history` (which ends with a user message) into a fresh assistant message. */
  const generate = async (conversationId: string, title: string, history: ChatMessage[], page: PageContext | null) => {
    const answerId = newId();
    const controller = new AbortController();
    controllerRef.current = controller;
    setStreaming(true);
    setAnnouncement(t('status.thinking'));
    const placeholder: ChatMessage = { id: answerId, role: 'assistant', content: '' };
    setConversations((all) =>
      [{ id: conversationId, title, messages: [...history, placeholder] }, ...all.filter((c) => c.id !== conversationId)].slice(0, MAX_CONVERSATIONS),
    );

    const patch = (change: (answer: ChatMessage) => ChatMessage) =>
      setConversations((all) =>
        all.map((conversation) =>
          conversation.id === conversationId
            ? { ...conversation, messages: conversation.messages.map((m) => (m.id === answerId ? change(m) : m)) }
            : conversation,
        ),
      );
    const finishTools = (answer: ChatMessage): ChatMessage => ({ ...answer, tools: answer.tools?.map((tool) => ({ ...tool, done: true })) });
    let failed = false;

    const onEvent = (event: AssistantEvent) => {
      if (event.type === 'sources') patch((answer) => ({ ...answer, sources: event.sources }));
      else if (event.type === 'tool') {
        setAnnouncement(event.label);
        patch((answer) => {
          const finished = finishTools(answer);
          return { ...finished, tools: [...(finished.tools ?? []), { label: event.label, done: false }] };
        });
      } else if (event.type === 'delta') patch((answer) => ({ ...finishTools(answer), content: answer.content + event.text }));
      else if (event.type === 'error') {
        failed = true;
        patch((answer) => ({ ...finishTools(answer), status: 'error', errorCode: event.code }));
        setAnnouncement(t('status.failed'));
      } else patch(finishTools);
    };

    try {
      const response = await apiStream(
        '/assistant/chat',
        {
          messages: history
            .slice(-MAX_API_MESSAGES)
            .filter((m) => m.content)
            .map(({ role, content }) => ({ role, content: content.slice(0, MAX_MESSAGE_LENGTH) })),
          ...(page && { page: { path: page.path, ...(page.entity && { entity: page.entity }) } }),
          language: i18n.language === 'kk' ? 'kk' : 'ru',
        },
        { signal: controller.signal },
      );
      await readEvents(response, onEvent);
      patch(finishTools);
      if (!failed) setAnnouncement(t('status.ready'));
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        patch((answer) => ({ ...finishTools(answer), status: 'stopped' }));
        setAnnouncement(t('status.stopped'));
      } else {
        patch((answer) => ({ ...finishTools(answer), status: 'error', errorCode: error instanceof ApiError ? error.code : 'network_error' }));
        setAnnouncement(t('status.failed'));
      }
    } finally {
      controllerRef.current = null;
      setStreaming(false);
    }
  };

  const send = (text: string, page: PageContext | null) => {
    const content = text.trim();
    if (!content || streaming) return;
    const userMessage: ChatMessage = { id: newId(), role: 'user', content };
    const conversationId = active?.id ?? newId();
    setActiveId(conversationId);
    void generate(conversationId, active?.title ?? titleFrom(content), [...messages, userMessage], page);
  };

  /** Asks again after a failed or stopped answer: the last answer is dropped and the question repeated. */
  const retry = (page: PageContext | null) => {
    if (!active || streaming) return;
    const history = messages.slice(0, -1);
    if (history.at(-1)?.role === 'user') void generate(active.id, active.title, history, page);
  };

  const startNew = () => {
    stop();
    setActiveId(null);
  };

  const select = (id: string) => {
    stop();
    setActiveId(id);
  };

  const remove = (id: string) => {
    if (id === activeId) startNew();
    setConversations((all) => all.filter((conversation) => conversation.id !== id));
  };

  return {
    conversations: conversations as Conversation[],
    active,
    messages,
    streaming,
    announcement,
    send,
    retry,
    stop,
    startNew,
    select,
    remove,
  };
}
