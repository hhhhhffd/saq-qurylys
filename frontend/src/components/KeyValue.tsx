import type { CSSProperties, ReactNode } from 'react';
import classes from './KeyValue.module.css';

export interface KeyValueItem {
  label: ReactNode;
  value: ReactNode;
  /** span both columns */
  wide?: boolean;
}

/** Definition list for passport-style data. Empty values render as an em dash. */
export function KeyValue({ items, columns = 2 }: { items: KeyValueItem[]; columns?: 1 | 2 | 3 }) {
  return (
    <dl className={classes.root} style={{ '--cols': columns } as CSSProperties}>
      {items.map((item, index) => (
        <div key={index} className={`${classes.item} ${item.wide ? classes.wide : ''}`}>
          <dt>{item.label}</dt>
          <dd>{item.value === null || item.value === undefined || item.value === '' ? '—' : item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
