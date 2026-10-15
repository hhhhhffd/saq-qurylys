import type { CSSProperties, ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface Props {
  title?: ReactNode;
  /** right side of the title row */
  actions?: ReactNode;
  children: ReactNode;
  /** remove inner padding (tables, maps) */
  flush?: boolean;
  className?: string;
  style?: CSSProperties;
  id?: string;
}

/** The Fatality group box: a thin frame, a caps title row, the body. */
export function Panel({ title, actions, children, flush, className, style, id }: Props) {
  return (
    <section id={id} className={cn('min-w-0 rounded border border-border bg-surface', className)} style={style}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-3 py-1.5">
          {title && <h3 className="font-heading text-2xs font-bold tracking-wider text-text uppercase">{title}</h3>}
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={flush ? undefined : 'p-3'}>{children}</div>
    </section>
  );
}
