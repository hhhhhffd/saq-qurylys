import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface Props {
  tone?: 'neutral' | 'warning';
  icon: ReactNode;
  title: ReactNode;
  children?: ReactNode;
  /** small line under the content (e.g. who and when) */
  meta?: ReactNode;
  /** keep line breaks of a free-text comment */
  multiline?: boolean;
}

/** Prominent note inside the card: a return comment, a recipient's answer, a warning before sending. */
export function Callout({ tone = 'neutral', icon, title, children, meta, multiline }: Props) {
  return (
    <div
      role="note"
      className={cn(
        'flex items-start gap-2.5 rounded border border-border bg-surface-sunken px-3 py-2.5 text-sm text-text',
        tone === 'warning' && 'border-zone-yellow/40 border-l-2 border-l-zone-yellow bg-zone-yellow-bg',
      )}
    >
      <span aria-hidden className="mt-0.5 flex-none text-text-2">
        {icon}
      </span>
      <div className="min-w-0">
        <h3 className="mb-0.5 font-heading text-xs font-bold tracking-wider uppercase">{title}</h3>
        {children && <div className={cn('break-words', multiline && 'whitespace-pre-wrap')}>{children}</div>}
        {meta && <p className="mt-1 text-xs text-text-3">{meta}</p>}
      </div>
    </div>
  );
}
