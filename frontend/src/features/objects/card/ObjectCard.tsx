import type { ObjectDetail } from '@/api/types';
import { ObjectHeader } from './ObjectHeader';
import { PassportSection } from './PassportSection';
import classes from './ObjectCard.module.css';

export function ObjectCard({ object }: { object: ObjectDetail }) {
  return (
    <div>
      <ObjectHeader object={object} />
      <div className={classes.layout}>
        <div className={classes.column}>
          <PassportSection object={object} />
        </div>
        <div className={classes.column} />
      </div>
    </div>
  );
}
