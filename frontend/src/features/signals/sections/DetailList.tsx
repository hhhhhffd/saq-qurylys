import { useTranslation } from 'react-i18next';
import { formatPlain, humanizeKey } from '../valueFormat';
import classes from './DetailList.module.css';

/** Backend-defined `detail` of a risk factor as readable key/value pairs. */
export function DetailList({ detail }: { detail: Record<string, unknown> | null }) {
  const { t } = useTranslation('signals');
  const { t: tc } = useTranslation();
  if (!detail) return null;
  const entries = Object.entries(detail);
  if (entries.length === 0) return null;

  const labels = { yes: tc('yes'), no: tc('no') };
  return (
    <dl className={classes.root}>
      {entries.map(([key, value]) => (
        <div key={key} className={classes.item}>
          <dt>{t(`detailKeys.${key}`, { defaultValue: humanizeKey(key) })}:</dt>
          <dd>{formatPlain(value, labels)}</dd>
        </div>
      ))}
    </dl>
  );
}
