import type { ReactNode } from 'react';
import classes from './PageHeader.module.css';

interface Props {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}

export function PageHeader({ title, subtitle, actions }: Props) {
  return (
    <div className={classes.root}>
      <div className={classes.text}>
        <h1>{title}</h1>
        {subtitle && <p className={classes.subtitle}>{subtitle}</p>}
      </div>
      {actions && <div className={classes.actions}>{actions}</div>}
    </div>
  );
}
