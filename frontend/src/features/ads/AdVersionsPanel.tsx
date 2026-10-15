import { Fragment, useId, useMemo } from 'react';
import { ActionIcon, CopyButton, Tooltip, VisuallyHidden } from '@mantine/core';
import { IconCheck, IconCopy } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import type { AdDetail } from '@/api/types';
import { Chip } from '@/components/Chip';
import { EvidenceImage } from '@/components/evidence/EvidenceImage';
import { useFormat } from '@/i18n/useFormat';
import { splitOcr } from './segments';
import { diffWords, type DiffPart } from './wordDiff';
import classes from './AdVersionsPanel.module.css';

const MINUTE_MS = 60_000;
const HOUR_MINUTES = 60;
const DAY_MINUTES = 24 * HOUR_MINUTES;

/** `2 ч 15 мин`; from a day on `3 д 2 ч`. */
function formatDuration(ms: number, units: { d: string; h: string; min: string; lessThanMinute: string }): string {
  const totalMinutes = Math.floor(ms / MINUTE_MS);
  if (totalMinutes < 1) return units.lessThanMinute;
  const days = Math.floor(totalMinutes / DAY_MINUTES);
  const hours = Math.floor((totalMinutes % DAY_MINUTES) / HOUR_MINUTES);
  const minutes = totalMinutes % HOUR_MINUTES;
  const parts =
    days > 0
      ? [`${days} ${units.d}`, hours > 0 ? `${hours} ${units.h}` : '']
      : [hours > 0 ? `${hours} ${units.h}` : '', minutes > 0 ? `${minutes} ${units.min}` : ''];
  return parts.filter(Boolean).join(' ');
}

const shortHash = (value: string) => `${value.slice(0, 8)}…${value.slice(-6)}`;

function Hash({ label, value }: { label: string; value: string }) {
  const { t } = useTranslation('ads');
  return (
    <span className={classes.hash}>
      <span className={classes.hashLabel}>{label}</span>
      <code className={classes.hashValue} title={value}>
        {shortHash(value)}
      </code>
      <CopyButton value={value} timeout={1800}>
        {({ copied, copy }) => (
          <>
            <Tooltip label={copied ? t('versions.copiedHash') : t('versions.copyHash')} withArrow>
              <ActionIcon size="sm" aria-label={t('versions.copyHash')} onClick={copy}>
                {copied ? <IconCheck size={14} stroke={2} /> : <IconCopy size={14} stroke={1.8} />}
              </ActionIcon>
            </Tooltip>
            {copied && <VisuallyHidden role="status">{t('versions.copiedHash')}</VisuallyHidden>}
          </>
        )}
      </CopyButton>
    </span>
  );
}

function DiffText({ parts, label }: { parts: DiffPart[]; label: string }) {
  return (
    // Scrolls when the text is long, so it must be reachable from the keyboard.
    <p className={classes.diffText} tabIndex={0} aria-label={label}>
      {parts.map((part, index) =>
        part.kind === 'removed' ? (
          <del key={index} className={classes.removed}>
            {part.text}
          </del>
        ) : part.kind === 'added' ? (
          <ins key={index} className={classes.added}>
            {part.text}
          </ins>
        ) : (
          <Fragment key={index}>{part.text}</Fragment>
        ),
      )}
    </p>
  );
}

interface Props {
  ad: AdDetail;
}

/**
 * «Удалили — а у нас осталось» (SPEC 10.6): when the publication was saved, what the source said later, and when
 * it was found removed, with the proof of each moment. Shown for a publication that has later versions or was removed.
 */
export function AdVersionsPanel({ ad }: Props) {
  const { t } = useTranslation('ads');
  const f = useFormat();
  const headingId = useId();
  const latest = ad.versions.at(-1);
  const removed = ad.status === 'removed_saved';
  // The comparison is with the publication's own text: the part read from its photos is not what the source showed.
  const original = splitOcr(ad.text ?? '', []).own.text;
  const diff = useMemo(() => (latest ? diffWords(original, latest.text) : null), [original, latest]);
  if (!latest && !removed) return null;

  const removedAfterMs = ad.removed_detected_at
    ? new Date(ad.removed_detected_at).getTime() - new Date(ad.original_captured_at).getTime()
    : Number.NaN;
  const removedAfter =
    Number.isFinite(removedAfterMs) && removedAfterMs >= 0
      ? formatDuration(removedAfterMs, {
          d: t('versions.units.d'),
          h: t('versions.units.h'),
          min: t('versions.units.min'),
          lessThanMinute: t('versions.units.lessThanMinute'),
        })
      : null;

  return (
    <section className={classes.panel} aria-labelledby={headingId}>
      <h3 id={headingId} className={classes.title}>
        {t('versions.title')}
      </h3>

      <ol className={classes.timeline}>
        <li className={classes.event}>
          <div className={classes.eventHead}>
            <strong>{t('versions.captured')}</strong>
            <time className="tnum" dateTime={ad.original_captured_at}>
              {f.dateTime(ad.original_captured_at)}
            </time>
          </div>
          {ad.original_evidence && (
            <div className={classes.proof}>
              <EvidenceImage
                id={ad.original_evidence.id}
                alt={t('versions.screenshot', { date: f.dateTime(ad.original_captured_at) })}
                size={56}
              />
              <div className={classes.proofText}>
                <Hash label={t('versions.screenshotHash')} value={ad.original_evidence.sha256} />
                {ad.original_evidence.has_tsa_token && <Chip outline>{t('versions.timestamp')}</Chip>}
              </div>
            </div>
          )}
        </li>

        {ad.versions.map((version) => (
          <li key={version.id} className={classes.event}>
            <div className={classes.eventHead}>
              <strong>{t('versions.changed')}</strong>
              <time className="tnum" dateTime={version.observed_at}>
                {f.dateTime(version.observed_at)}
              </time>
              <span className="faint">({t(`versions.source.${version.source}`)})</span>
            </div>
            <div className={classes.proof}>
              {version.evidence_id !== null && (
                <EvidenceImage
                  id={version.evidence_id}
                  alt={t('versions.screenshot', { date: f.dateTime(version.observed_at) })}
                  size={56}
                />
              )}
              <div className={classes.proofText}>
                <Hash label={t('versions.textHash')} value={version.text_sha256} />
              </div>
            </div>
          </li>
        ))}

        {removed && ad.removed_detected_at && (
          <li className={`${classes.event} ${classes.eventRemoved}`}>
            <div className={classes.eventHead}>
              <strong>{t('versions.removed')}</strong>
              <time className="tnum" dateTime={ad.removed_detected_at}>
                {f.dateTime(ad.removed_detected_at)}
              </time>
            </div>
            {removedAfter && <p className={classes.removedAfter}>{t('versions.removedAfter', { duration: removedAfter })}</p>}
            <p className={`faint ${classes.note}`}>{t('versions.removedNote')}</p>
          </li>
        )}
      </ol>

      {diff && latest && (
        <div className={classes.compare}>
          <h4 className={classes.subtitle}>{t('versions.compare')}</h4>
          <div className={classes.panes}>
            <div className={classes.pane}>
              <div className={classes.paneHead}>
                <strong>{t('versions.original')}</strong>
                <span className="faint tnum">{f.dateTime(ad.original_captured_at)}</span>
              </div>
              <DiffText parts={diff.before} label={t('versions.original')} />
            </div>
            <div className={classes.pane}>
              <div className={classes.paneHead}>
                <strong>{t('versions.current')}</strong>
                <span className="faint tnum">{t('versions.asOf', { date: f.dateTime(latest.observed_at) })}</span>
              </div>
              <DiffText parts={diff.after} label={t('versions.current')} />
            </div>
          </div>
          <p className={`faint ${classes.note}`}>{t('versions.legend')}</p>
        </div>
      )}
    </section>
  );
}
