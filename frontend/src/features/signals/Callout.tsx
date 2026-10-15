import type { ReactNode } from 'react';
import classes from './Callout.module.css';

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
    <div className={`${classes.root} ${tone === 'warning' ? classes.warning : ''}`} role="note">
      <span className={classes.icon} aria-hidden>
        {icon}
      </span>
      <div className={classes.body}>
        <h3 className={classes.title}>{title}</h3>
        {children && <div className={`${classes.content} ${multiline ? classes.multiline : ''}`}>{children}</div>}
        {meta && <p className={classes.meta}>{meta}</p>}
      </div>
    </div>
  );
}
