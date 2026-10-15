import { useTranslation } from 'react-i18next';
import type { AuditEntry } from '@/api/types';
import { Panel } from '@/components/Panel';
import { useEnum, type EnumGroup } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { auditActionKey } from './auditActions';
import { auditDiff } from './auditDiff';
import { formatPlain, humanizeKey } from './valueFormat';
import classes from './AuditTimeline.module.css';

const MAX_ROWS = 20;

// Fields whose values are backend codes with a translation.
const ENUM_FIELDS: Record<string, EnumGroup> = {
  status: 'signal_status',
  recipient: 'recipient',
  origin: 'origin',
  proposed_measures: 'measure',
  payment_schemes: 'payment_scheme',
};

function byNewest(a: AuditEntry, b: AuditEntry): number {
  return new Date(b.at).getTime() - new Date(a.at).getTime() || b.id - a.id;
}

export function AuditTimeline({ entries }: { entries: AuditEntry[] }) {
  const { t } = useTranslation('signals');
  const { t: tc } = useTranslation();
  const e = useEnum();
  const { date, dateTime } = useFormat();
  const labels = { yes: tc('yes'), no: tc('no') };

  const formatValue = (field: string, value: unknown): string => {
    const group = ENUM_FIELDS[field];
    if (group && typeof value === 'string') return e(group, value);
    if (group && Array.isArray(value) && value.every((item) => typeof item === 'string')) {
      return value.length === 0 ? '—' : value.map((item: string) => e(group, item)).join(', ');
    }
    if (typeof value === 'string' && field.endsWith('_at')) return dateTime(value);
    if (typeof value === 'string' && field.endsWith('_date')) return date(value);
    return formatPlain(value, labels);
  };

  return (
    <Panel title={t('audit.title')}>
      {entries.length === 0 ? (
        <p className="faint">{t('audit.empty')}</p>
      ) : (
        <ol className={classes.list}>
          {[...entries].sort(byNewest).map((entry) => {
            const key = auditActionKey(entry.action);
            const rows = auditDiff(entry.before, entry.after);
            const user = entry.username ?? (entry.user_id === null ? t('audit.system') : `#${entry.user_id}`);
            return (
              <li key={entry.id} className={classes.entry}>
                <div className={classes.head}>
                  <span className={classes.action}>{key ? t(`audit.actions.${key}`) : entry.action}</span>
                  <span className={classes.meta}>
                    {user} · {dateTime(entry.at)}
                  </span>
                </div>
                {rows.length > 0 && (
                  <details className={classes.changes}>
                    <summary>{t('audit.changes', { count: rows.length })}</summary>
                    <dl className={classes.rows}>
                      {rows.slice(0, MAX_ROWS).map((row) => {
                        const field = row.path.split('.').pop() ?? row.path;
                        return (
                          <div key={row.path} className={classes.row}>
                            <dt>{t(`audit.fields.${field}`, { defaultValue: humanizeKey(field) })}</dt>
                            <dd>
                              <del className={classes.from}>{formatValue(field, row.before)}</del>
                              <span className={classes.arrow} aria-hidden>
                                →
                              </span>
                              <ins className={classes.to}>{formatValue(field, row.after)}</ins>
                            </dd>
                          </div>
                        );
                      })}
                    </dl>
                    {rows.length > MAX_ROWS && (
                      <p className={classes.more}>{t('audit.more', { count: rows.length - MAX_ROWS })}</p>
                    )}
                  </details>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </Panel>
  );
}
