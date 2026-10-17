/** Types, SSE reading and local history of the assistant chat (docs/ASSISTANT.md). */

export interface AssistantSource {
  id: string;
  title: string;
  page: string | null;
}

export interface ToolStep {
  label: string;
  done: boolean;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: AssistantSource[];
  tools?: ToolStep[];
  /** how an assistant answer ended abnormally */
  status?: 'error' | 'stopped';
  errorCode?: string;
}

export interface Conversation {
  id: string;
  title: string;
  messages: ChatMessage[];
}

export type AssistantEvent =
  | { type: 'sources'; sources: AssistantSource[] }
  | { type: 'tool'; name: string; label: string }
  | { type: 'delta'; text: string }
  | { type: 'error'; code: string; message: string }
  | { type: 'done' };

export const MAX_CONVERSATIONS = 20;
export const MAX_API_MESSAGES = 20;
export const MAX_MESSAGE_LENGTH = 4000;
const TITLE_LENGTH = 60;

export function titleFrom(text: string): string {
  const line = text.trim().replace(/\s+/g, ' ');
  return line.length > TITLE_LENGTH ? `${line.slice(0, TITLE_LENGTH - 1)}…` : line;
}

/** Reads `data: <json>` frames separated by blank lines; a frame may arrive split across chunks. */
export async function readEvents(response: Response, onEvent: (event: AssistantEvent) => void): Promise<void> {
  if (!response.body) throw new Error('The response has no body');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const handleFrame = (frame: string) => {
    const data = frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).replace(/^ /, ''))
      .join('\n');
    if (data) onEvent(JSON.parse(data) as AssistantEvent);
  };

  for (;;) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? '';
    frames.forEach(handleFrame);
    if (done) break;
  }
  handleFrame(buffer);
}

// ---------------------------------------------------------------- history (this browser only)

const storageKey = (userId: number) => `saq_ai_conversations_${userId}`;

export function loadConversations(userId: number): Conversation[] {
  try {
    const raw = localStorage.getItem(storageKey(userId));
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? (parsed as Conversation[]).slice(0, MAX_CONVERSATIONS) : [];
  } catch {
    return [];
  }
}

export function saveConversations(userId: number, conversations: Conversation[]): void {
  try {
    localStorage.setItem(storageKey(userId), JSON.stringify(conversations));
  } catch {
    // History is best-effort: storage can be blocked or full.
  }
}
