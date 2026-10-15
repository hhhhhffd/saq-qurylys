import type { ReactNode } from 'react';
import classes from './AdminPage.module.css';

interface Props {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

export function SectionHeader({ title, description, actions }: Props) {
  return (
    <div className={classes.header}>
      <div className={classes.headerText}>
        <h2 className={classes.sectionTitle}>{title}</h2>
        {description && <p className={classes.description}>{description}</p>}
      </div>
      {actions && <div className={classes.headerActions}>{actions}</div>}
    </div>
  );
}
