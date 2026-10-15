import { useTranslation } from 'react-i18next';
import type { GraphNodeType } from '@/api/types';
import classes from './Legend.module.css';

const TYPES: readonly GraphNodeType[] = ['developer', 'object', 'phone', 'account', 'ad'];

// Same shapes and colors as the canvas (LinkGraphCanvas, palette.ts), drawn with the theme variables.
function Swatch({ type }: { type: GraphNodeType }) {
  return (
    <svg className={classes.swatch} viewBox="-9 -9 18 18" aria-hidden>
      {type === 'developer' && <rect x="-7" y="-7" width="14" height="14" rx="4" fill="var(--accent)" />}
      {type === 'object' && <circle r="7" fill="var(--zone-none)" />}
      {type === 'phone' && <path d="M0 -7 L7 0 L0 7 L-7 0 Z" fill="var(--link)" />}
      {type === 'account' && <path d="M0 -7 L6.6 5 L-6.6 5 Z" fill="var(--text-2)" />}
      {type === 'ad' && <circle r="3.5" fill="var(--text-3)" />}
    </svg>
  );
}

export function Legend() {
  const { t } = useTranslation('graph');
  return (
    <ul className={classes.root} aria-label={t('legend.label')}>
      {TYPES.map((type) => (
        <li key={type} className={classes.item}>
          <Swatch type={type} />
          {t(`legend.${type}`)}
          {type === 'object' && (
            <span className={classes.zones} aria-hidden>
              {(['green', 'yellow', 'red'] as const).map((zone) => (
                <span key={zone} className={classes.zone} style={{ background: `var(--zone-${zone})` }} />
              ))}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}
