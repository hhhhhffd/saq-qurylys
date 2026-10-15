import type { ReactNode } from 'react';
import classes from './Chip.module.css';

export type ChipTone = 'neutral' | 'green' | 'yellow' | 'red' | 'info';

interface Props {
  tone?: ChipTone;
  children: ReactNode;
  /** subtle outline variant (e.g. "AI assumption" marker) */
  outline?: boolean;
  title?: string;
}

/** Small status label. Tones reuse zone colors; keep them for semantics (ok / warning / danger). */
export function Chip({ tone = 'neutral', children, outline, title }: Props) {
  return (
    <span className={`${classes.chip} ${classes[tone]} ${outline ? classes.outline : ''}`} title={title}>
      {children}
    </span>
  );
}
