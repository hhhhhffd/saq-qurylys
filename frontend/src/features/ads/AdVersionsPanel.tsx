import { Fragment, useEffect, useId, useMemo, useRef, useState } from 'react';
import { IconCheck, IconCopy } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import type { AdDetail } from '@/api/types';
import { Chip } from '@/components/Chip';
import { EvidenceImage } from '@/components/evidence/EvidenceImage';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useFormat } from '@/i18n/useFormat';
import { toast } from '@/lib/toast';
import { cn } from '@/lib/utils';
import { splitOcr } from './segments';
import { diffWords, type DiffPart } from './wordDiff';

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

const COPIED_MS = 1800;

function Hash({ label, value }: { label: string; value: string }) {
  const { t } = useTranslation('ads');
  const { t: tc } = useTranslation('common');
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const copy = () => {
    navigator.clipboard.writeText(value).then(
      () => {
        setCopied(true);
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => setCopied(false), COPIED_MS);
      },
      () => toast.error(tc('error')),
    );
  };

  return (
    <span className="inline-flex min-w-0 flex-wrap items-center gap-x-1.5">
      <span className="text-xs text-text-3">{label}</span>
      <code className="rounded-sm bg-surface-sunken px-1.5 py-px font-mono text-xs text-text-2" title={value}>
        {shortHash(value)}
      </code>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button size="icon-xs" variant="ghost" aria-label={t('versions.copyHash')} onClick={copy}>
            {copied ? <IconCheck /> : <IconCopy />}
          </Button>
        </TooltipTrigger>
        <TooltipContent>{copied ? t('versions.copiedHash') : t('versions.copyHash')}</TooltipContent>
      </Tooltip>
      {copied && (
        <span className="sr-only" role="status">
          {t('versions.copiedHash')}
        </span>
      )}
    </span>
  );
}

function DiffText({ parts, label }: { parts: DiffPart[]; label: string }) {
  return (
    // Scrolls when the text is long, so it must be reachable from the keyboard.
    <p
      className="m-0 max-h-88 overflow-y-auto font-sans text-sm leading-relaxed [overflow-wrap:anywhere] whitespace-pre-wrap overscroll-contain"
      tabIndex={0}
      aria-label={label}
    >
      {parts.map((part, index) =>
        part.kind === 'removed' ? (
          <del
            key={index}
            className="rounded-[3px] bg-zone-red-bg px-px text-zone-red-ink decoration-1 line-through"
          >
            {part.text}
          </del>
        ) : part.kind === 'added' ? (
          <ins key={index} className="rounded-[3px] bg-zone-green-bg px-px text-zone-green-ink no-underline">
            {part.text}
          </ins>
        ) : (
          <Fragment key={index}>{part.text}</Fragment>
        ),
      )}
    </p>
  );
}

const headingClass = 'm-0 font-heading text-2xs font-bold tracking-wider text-text uppercase';
const noteClass = 'm-0 text-xs text-text-3';

/** One moment of the timeline: a dot on a quiet vertical line. */
function TimelineEvent({ removed = false, children }: { removed?: boolean; children: React.ReactNode }) {
  return (
    <li
      className={cn(
        'relative flex min-w-0 flex-col gap-1.5 pb-4 pl-5 text-sm last:pb-0',
        'before:absolute before:top-1.5 before:left-0 before:size-2.5 before:rounded-full before:ring-4 before:ring-surface',
        removed ? 'before:bg-zone-red' : 'before:bg-text-3',
        'after:absolute after:top-4 after:bottom-0 after:left-[4.5px] after:w-px after:bg-border-strong last:after:hidden',
      )}
    >
      {children}
    </li>
  );
}

const eventHeadClass = 'flex flex-wrap items-baseline gap-x-2 gap-y-0.5';
const proofClass = 'flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2';

interface Props {
  ad: AdDetail;
}

/**
 * «Удалили — а у нас осталось» (SPEC 10.6): when the publication was saved, what the source said later, and when
 * it was found removed, with the proof of each moment. Shown for a publication that has later versions or was found
 * removed (`removed_detected_at`): a removed post whose link is not confirmed keeps the status `verification`.
 */
export function AdVersionsPanel({ ad }: Props) {
  const { t } = useTranslation('ads');
  const f = useFormat();
  const headingId = useId();
  const latest = ad.versions.at(-1);
  const removedAt = ad.removed_detected_at;
  // The comparison is with the publication's own text: the part read from its photos is not what the source showed.
  const original = splitOcr(ad.text ?? '', []).own.text;
  const diff = useMemo(() => (latest ? diffWords(original, latest.text) : null), [original, latest]);
  if (!latest && removedAt === null) return null;

  const removedAfterMs = removedAt
    ? new Date(removedAt).getTime() - new Date(ad.original_captured_at).getTime()
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
    <section className="flex min-w-0 flex-col gap-3.5 border-t border-border pt-3" aria-labelledby={headingId}>
      <h3 id={headingId} className={headingClass}>
        {t('versions.title')}
      </h3>

      <ol className="m-0 flex list-none flex-col p-0">
        <TimelineEvent>
          <div className={eventHeadClass}>
            <strong>{t('versions.captured')}</strong>
            <time className="text-text-2 tabular-nums" dateTime={ad.original_captured_at}>
              {f.dateTime(ad.original_captured_at)}
            </time>
          </div>
          {ad.original_evidence && (
            <div className={proofClass}>
              <EvidenceImage
                id={ad.original_evidence.id}
                alt={t('versions.screenshot', { date: f.dateTime(ad.original_captured_at) })}
                size={56}
              />
              <div className="flex min-w-0 flex-col items-start gap-1">
                <Hash label={t('versions.screenshotHash')} value={ad.original_evidence.sha256} />
                {ad.original_evidence.has_tsa_token && <Chip outline>{t('versions.timestamp')}</Chip>}
              </div>
            </div>
          )}
        </TimelineEvent>

        {ad.versions.map((version) => (
          <TimelineEvent key={version.id}>
            <div className={eventHeadClass}>
              <strong>{t('versions.changed')}</strong>
              <time className="text-text-2 tabular-nums" dateTime={version.observed_at}>
                {f.dateTime(version.observed_at)}
              </time>
              <span className="text-text-3">({t(`versions.source.${version.source}`)})</span>
            </div>
            <div className={proofClass}>
              {version.evidence_id !== null && (
                <EvidenceImage
                  id={version.evidence_id}
                  alt={t('versions.screenshot', { date: f.dateTime(version.observed_at) })}
                  size={56}
                />
              )}
              <div className="flex min-w-0 flex-col items-start gap-1">
                <Hash label={t('versions.textHash')} value={version.text_sha256} />
              </div>
            </div>
          </TimelineEvent>
        ))}

        {removedAt && (
          <TimelineEvent removed>
            <div className={eventHeadClass}>
              <strong>{t('versions.removed')}</strong>
              <time className="text-text-2 tabular-nums" dateTime={removedAt}>
                {f.dateTime(removedAt)}
              </time>
            </div>
            {removedAfter && (
              <p className="m-0 font-semibold text-zone-red-ink">{t('versions.removedAfter', { duration: removedAfter })}</p>
            )}
            <p className={noteClass}>{t('versions.removedNote')}</p>
          </TimelineEvent>
        )}
      </ol>

      {diff && latest && (
        <div className="flex flex-col gap-2">
          <h4 className={headingClass}>{t('versions.compare')}</h4>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,260px),1fr))] gap-2.5">
            <div className="flex min-w-0 flex-col gap-1.5 rounded border border-border bg-surface-sunken px-3 py-2.5">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm">
                <strong>{t('versions.original')}</strong>
                <span className="text-xs text-text-3 tabular-nums">{f.dateTime(ad.original_captured_at)}</span>
              </div>
              <DiffText parts={diff.before} label={t('versions.original')} />
            </div>
            <div className="flex min-w-0 flex-col gap-1.5 rounded border border-border bg-surface-sunken px-3 py-2.5">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm">
                <strong>{t('versions.current')}</strong>
                <span className="text-xs text-text-3 tabular-nums">
                  {t('versions.asOf', { date: f.dateTime(latest.observed_at) })}
                </span>
              </div>
              <DiffText parts={diff.after} label={t('versions.current')} />
            </div>
          </div>
          <p className={noteClass}>{t('versions.legend')}</p>
        </div>
      )}
    </section>
  );
}
