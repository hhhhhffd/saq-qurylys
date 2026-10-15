import type { CSSProperties, ReactNode } from 'react';
import classes from './Panel.module.css';

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

export function Panel({ title, actions, children, flush, className, style, id }: Props) {
  return (
    <section id={id} className={`panel ${classes.root} ${className ?? ''}`} style={style}>
      {(title || actions) && (
        <header className={classes.header}>
          {title && <h3 className={classes.title}>{title}</h3>}
          {actions && <div className={classes.actions}>{actions}</div>}
        </header>
      )}
      <div className={flush ? classes.flush : classes.body}>{children}</div>
    </section>
  );
}
