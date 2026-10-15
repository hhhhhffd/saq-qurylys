import { useTranslation } from 'react-i18next';
import type { AuditEntry } from '@/api/types';
import { Panel } from '@/components/Panel';
import { useEnum, type EnumGroup } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import { auditActionKey } from './auditActions';
import { auditDiff } from './auditDiff';
import { formatPlain, humanizeKey } from './valueFormat';

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
        <p className="text-text-3">{t('audit.empty')}</p>
      ) : (
        <ol className="relative m-0 flex list-none flex-col gap-2.5 p-0 pl-4 before:absolute before:top-1.5 before:bottom-1.5 before:left-[3px] before:w-px before:bg-border-strong">
          {[...entries].sort(byNewest).map((entry) => {
            const key = auditActionKey(entry.action);
            const rows = auditDiff(entry.before, entry.after);
            const user = entry.username ?? (entry.user_id === null ? t('audit.system') : `#${entry.user_id}`);
            return (
              <li
                key={entry.id}
                className="relative min-w-0 before:absolute before:top-[5px] before:-left-4 before:size-[7px] before:rounded-full before:bg-surface before:ring-2 before:ring-text-3 first:before:bg-primary first:before:ring-primary"
              >
                <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-0.5">
                  <span className="text-sm font-semibold">{key ? t(`audit.actions.${key}`) : entry.action}</span>
                  <span className="text-xs text-text-3 tabular-nums">
                    {user} · {dateTime(entry.at)}
                  </span>
                </div>
                {rows.length > 0 && (
                  <details className="mt-0.5 text-xs">
                    <summary className="inline-block cursor-pointer text-link hover:underline">{t('audit.changes', { count: rows.length })}</summary>
                    <dl className="mt-1.5 grid grid-cols-1 gap-x-3.5 gap-y-1 rounded border border-border bg-surface-sunken px-3 py-2 sm:grid-cols-[max-content_minmax(0,1fr)]">
                      {rows.slice(0, MAX_ROWS).map((row) => {
                        const field = row.path.split('.').pop() ?? row.path;
                        return (
                          <div key={row.path} className="contents">
                            <dt className="text-text-2">{t(`audit.fields.${field}`, { defaultValue: humanizeKey(field) })}</dt>
                            <dd className="m-0 break-words">
                              <del className="text-text-3">{formatValue(field, row.before)}</del>
                              <span className="mx-1.5 text-text-3" aria-hidden>
                                →
                              </span>
                              <ins className="no-underline">{formatValue(field, row.after)}</ins>
                            </dd>
                          </div>
                        );
                      })}
                    </dl>
                    {rows.length > MAX_ROWS && (
                      <p className="mt-1.5 text-text-3">{t('audit.more', { count: rows.length - MAX_ROWS })}</p>
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
