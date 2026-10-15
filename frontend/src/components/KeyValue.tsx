import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface KeyValueItem {
  label: ReactNode;
  value: ReactNode;
  /** span both columns */
  wide?: boolean;
}

const COLUMNS = { 1: '', 2: 'sm:grid-cols-2', 3: 'sm:grid-cols-3' } as const;

/** Definition list for passport-style data. Empty values render as an em dash. */
export function KeyValue({ items, columns = 2 }: { items: KeyValueItem[]; columns?: 1 | 2 | 3 }) {
  return (
    <dl className={cn('m-0 grid grid-cols-1 gap-x-6 gap-y-3', COLUMNS[columns])}>
      {items.map((item, index) => (
        <div key={index} className={cn('min-w-0', item.wide && 'col-span-full')}>
          <dt className="mb-0.5 text-xs text-text-3">{item.label}</dt>
          <dd className="m-0 text-text [overflow-wrap:anywhere]">
            {item.value === null || item.value === undefined || item.value === '' ? '—' : item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
