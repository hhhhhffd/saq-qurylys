import { Fragment } from 'react';
import { useTranslation } from 'react-i18next';
import { useEnum, type EnumGroup } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import classes from './FactorDetail.module.css';

/** Groups that can hold a code found in a factor's `detail` payload. */
const CODE_GROUPS: EnumGroup[] = [
  'doc_type',
  'payment_scheme',
  'phrase_category',
  'check_status',
  'legal_basis_status',
  'construction_status',
  'complaint_status',
  'platform',
];
const CODE = /^[a-z][a-z0-9_]*$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}(?:T.*)?$/;

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function DetailValue({ value }: { value: unknown }) {
  const { t } = useTranslation();
  const e = useEnum();
  const { date, dateTime, number } = useFormat();

  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'boolean') return t(value ? 'yes' : 'no');
  if (typeof value === 'number') return number(value);
  if (typeof value === 'string') {
    if (ISO_DATE.test(value)) return value.length === 10 ? date(value) : dateTime(value);
    if (!CODE.test(value)) return value;
    const group = CODE_GROUPS.find((candidate) => e(candidate, value) !== value);
    return group ? e(group, value) : value;
  }
  if (Array.isArray(value)) {
    if (value.some(isObject)) {
      return (
        <ul className={classes.list}>
          {value.map((item, index) => (
            <li key={index}>
              <DetailValue value={item} />
            </li>
          ))}
        </ul>
      );
    }
    return value.map((item, index) => (
      <Fragment key={index}>
        {index > 0 && ', '}
        <DetailValue value={item} />
      </Fragment>
    ));
  }
  if (isObject(value)) return <FactorDetail detail={value} />;
  return String(value);
}

/** `detail` of a score factor as readable key/value pairs (nested objects such as R1 `checks` are indented). */
export function FactorDetail({ detail }: { detail: object }) {
  const { t } = useTranslation('objects');
  return (
    <dl className={classes.root}>
      {Object.entries(detail).map(([key, value]) => (
        <Fragment key={key}>
          <dt>{t(`card.breakdown.detailKeys.${key}`, { defaultValue: key.replace(/_/g, ' ') })}</dt>
          <dd>
            <DetailValue value={value} />
          </dd>
        </Fragment>
      ))}
    </dl>
  );
}
