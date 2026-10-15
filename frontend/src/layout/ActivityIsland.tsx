import { useEffect, useReducer, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { VisuallyHidden } from '@mantine/core';
import { useReducedMotion } from '@mantine/hooks';
import {
  IconArrowRight,
  IconArrowsExchange,
  IconFilePlus,
  IconMessageReport,
  IconSend,
  IconSpeakerphone,
  IconTrendingDown,
  IconTrendingUp,
} from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { useActivityFeed } from '@/api/hooks/activity';
import type { ActivityEvent } from '@/api/types';
import { zoneColor } from '@/components/zoneColor';
import { useEnum } from '@/i18n/useEnum';
import classes from './ActivityIsland.module.css';

/** How long an event stays open; shorter when others wait, and after the pointer leaves. */
const OPEN_MS = 6000;
const OPEN_BUSY_MS = 3800;
const OPEN_RESUMED_MS = 2500;
/** Events waiting for their turn; a long absence of the tab must not turn into minutes of animation. */
const MAX_WAITING = 5;
const SCORE_DELAY_MS = 320;
const SCORE_TWEEN_MS = 760;

/** Sizes in px; the stylesheet repeats the two heights. */
const IDLE_WIDTH = 132;
const IDLE_HEIGHT = 32;
const OPEN_WIDTH = 400;
const OPEN_HEIGHT = 48;
/** With less room than this the idle island shrinks to its dot. */
const MIN_LABEL_ROOM = 100;
/** Distance from the screen edge when the open island is as wide as the screen allows. */
const EDGE_GAP = 16;

interface Presentation {
  icon: ReactNode;
  title: string;
  detail: string;
  /** read out by screen readers; the visual content is decorative */
  announcement: string;
  /** entered the red zone: a slightly stronger accent */
  alert: boolean;
  target: string;
}

function usePresentation(): (event: ActivityEvent) => Presentation {
  const { t } = useTranslation('activity');
  const e = useEnum();

  return (event) => {
    const join = (...parts: (string | null)[]) => parts.filter(Boolean).join(' · ');
    const plain = (icon: ReactNode, title: string, detail: string, target: string): Presentation => ({
      icon,
      title,
      detail,
      announcement: `${title}. ${detail}`,
      alert: false,
      target,
    });

    switch (event.kind) {
      case 'ad_received': {
        const citizen = event.origin === 'citizen';
        const title = citizen
          ? t('title.adCitizen')
          : event.origin === 'collector'
            ? t('title.adCollector')
            : t('title.adStaff');
        return plain(
          citizen ? <IconMessageReport /> : <IconSpeakerphone />,
          title,
          join(event.object_name, e('platform', event.platform)),
          `/ads?ad=${event.ad_id}`,
        );
      }
      case 'signal_created':
        return plain(
          <IconFilePlus />,
          t('title.signalCreated'),
          join(event.number, event.object_name),
          `/signals/${event.signal_id}`,
        );
      case 'signal_sent':
        return plain(
          <IconSend />,
          t('title.signalSent'),
          join(event.number, event.object_name),
          `/signals/${event.signal_id}`,
        );
      case 'score_changed': {
        const object = event.object_name ?? '';
        const before = event.score_before ?? 0;
        const after = event.score_after ?? before;
        const zoneTo = e('zone', event.zone_after);
        const detail =
          event.zone_before !== event.zone_after
            ? t('score.zone', { from: e('zone', event.zone_before), to: zoneTo })
            : after > before
              ? t('score.up')
              : t('score.down');
        return {
          icon: after > before ? <IconTrendingUp /> : after < before ? <IconTrendingDown /> : <IconArrowsExchange />,
          title: object,
          detail,
          announcement: `${object}. ${t('score.announce', { from: before, to: after, zone: zoneTo })}`,
          alert: event.zone_after === 'red' && event.zone_before !== 'red',
          target: `/objects/${event.object_id}`,
        };
      }
    }
  };
}

const easeOutCubic = (progress: number) => 1 - (1 - progress) ** 3;

/** `45 → 70`: the second number counts up (or down) and the dot changes to the new zone's color. */
function ScoreShift({ event, instant }: { event: ActivityEvent; instant: boolean }) {
  const from = event.score_before ?? 0;
  const to = event.score_after ?? from;
  const [counted, setCounted] = useState(from);
  const [zone, setZone] = useState(event.zone_before);

  useEffect(() => {
    if (instant) return;
    let frame = 0;
    const timer = window.setTimeout(() => {
      setZone(event.zone_after);
      const started = performance.now();
      const step = (now: number) => {
        const progress = Math.min(1, (now - started) / SCORE_TWEEN_MS);
        setCounted(Math.round(from + (to - from) * easeOutCubic(progress)));
        if (progress < 1) frame = requestAnimationFrame(step);
      };
      frame = requestAnimationFrame(step);
    }, SCORE_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
      cancelAnimationFrame(frame);
    };
  }, [instant, event.zone_after, from, to]);

  return (
    <span className={`${classes.score} tnum`} aria-hidden>
      <span className={classes.scoreFrom}>{from}</span>
      <IconArrowRight size={13} stroke={2} />
      <span className={classes.scoreTo}>{instant ? to : counted}</span>
      <span className={classes.zoneDot} style={{ background: zoneColor(instant ? event.zone_after : zone) }} />
    </span>
  );
}

// ---------------------------------------------------------------- what is on show

interface IslandState {
  /** the event on show; it stays rendered while the island collapses so that it can fade out */
  shown: ActivityEvent | null;
  open: boolean;
  waiting: ActivityEvent[];
}

type IslandAction = { type: 'events'; events: ActivityEvent[] } | { type: 'advance' } | { type: 'close' };

function reduce(state: IslandState, action: IslandAction): IslandState {
  switch (action.type) {
    case 'events': {
      const queued = [...state.waiting, ...action.events].slice(-MAX_WAITING);
      // An idle island takes the oldest of them at once, an open one lets them wait their turn.
      return state.open ? { ...state, waiting: queued } : { shown: queued[0], open: true, waiting: queued.slice(1) };
    }
    case 'advance':
      return state.waiting.length > 0
        ? { shown: state.waiting[0], open: true, waiting: state.waiting.slice(1) }
        : { ...state, open: false };
    case 'close':
      return { ...state, open: false };
  }
}

// ---------------------------------------------------------------- where it goes

/** Where the island goes, in px relative to the header (its positioning context). */
interface Geometry {
  /** vertical middle of the header row the island lives in */
  mid: number;
  idleWidth: number;
  openWidth: number;
  /** horizontal offsets from the center of the header */
  idleShift: number;
  openShift: number;
  /** the open island fits into the header row; otherwise it hangs below the header */
  inBand: boolean;
}

const clamp = (value: number, min: number, max: number) =>
  min > max ? (min + max) / 2 : Math.min(Math.max(value, min), max);

/**
 * The header leaves the island a slot between the navigation and the tools (between the wordmark and the tools
 * when the header wraps). The island sits at the center of the screen when the slot reaches it and as near as
 * the slot allows otherwise, so it never covers the navigation. An open island that does not fit into the slot
 * hangs below the header instead.
 */
function useGeometry() {
  const slotRef = useRef<HTMLDivElement>(null);
  const [geometry, setGeometry] = useState<Geometry | null>(null);

  useEffect(() => {
    const slot = slotRef.current;
    const header = slot?.offsetParent;
    if (!slot || !header) return;
    const measure = () => {
      const bounds = header.getBoundingClientRect();
      const box = slot.getBoundingClientRect();
      const left = box.left - bounds.left;
      const right = box.right - bounds.left;
      const center = bounds.width / 2;
      const idleWidth = box.width < MIN_LABEL_ROOM ? IDLE_HEIGHT : Math.min(IDLE_WIDTH, box.width);
      const openWidth = Math.min(OPEN_WIDTH, bounds.width - 2 * EDGE_GAP);
      const inBand = box.width >= openWidth && box.height >= OPEN_HEIGHT;
      setGeometry({
        mid: box.top - bounds.top + box.height / 2,
        idleWidth,
        openWidth,
        idleShift: clamp(center, left + idleWidth / 2, right - idleWidth / 2) - center,
        openShift: inBand ? clamp(center, left + openWidth / 2, right - openWidth / 2) - center : 0,
        inBand,
      });
    };
    // Fires once on start, before the first paint, and whenever the header or the room in it changes.
    const observer = new ResizeObserver(measure);
    observer.observe(slot);
    observer.observe(header);
    return () => observer.disconnect();
  }, []);

  return { slotRef, geometry };
}

export function ActivityIsland() {
  const { t } = useTranslation('activity');
  const { t: tc } = useTranslation();
  const navigate = useNavigate();
  const present = usePresentation();
  const reduced = useReducedMotion(false, { getInitialValueInEffect: false });

  const [{ shown, open, waiting }, dispatch] = useReducer(reduce, { shown: null, open: false, waiting: [] });
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  // The pointer or focus left an open event: it gets a short grace period instead of a full one.
  const resumed = useRef(false);

  const { slotRef, geometry } = useGeometry();
  const feed = useActivityFeed((events) => dispatch({ type: 'events', events }));

  const held = hovered || focused;
  const hasWaiting = waiting.length > 0;
  useEffect(() => {
    if (!open || held) return;
    const delay = resumed.current ? OPEN_RESUMED_MS : hasWaiting ? OPEN_BUSY_MS : OPEN_MS;
    const timer = window.setTimeout(() => {
      resumed.current = false;
      dispatch({ type: 'advance' });
    }, delay);
    return () => window.clearTimeout(timer);
  }, [open, held, shown, hasWaiting]);

  const content = shown ? present(shown) : null;
  const style: CSSProperties | undefined = geometry
    ? ({
        '--mid': `${geometry.mid}px`,
        '--w-idle': `${geometry.idleWidth}px`,
        '--w-open': `${geometry.openWidth}px`,
        '--shift-idle': `${geometry.idleShift}px`,
        '--shift-open': `${geometry.openShift}px`,
      } as CSSProperties)
    : undefined;

  return (
    <div ref={slotRef} className={classes.slot}>
      <VisuallyHidden role="status" aria-live="polite" aria-atomic="true">
        {open && content ? content.announcement : ''}
      </VisuallyHidden>
      {geometry && (
        <div
          className={classes.island}
          style={style}
          data-open={open}
          data-place={geometry.inBand ? 'band' : 'below'}
          data-compact={geometry.idleWidth < MIN_LABEL_ROOM}
          data-alert={open && content?.alert === true}
          data-offline={feed.isError}
          onPointerEnter={() => {
            resumed.current = true;
            setHovered(true);
          }}
          onPointerLeave={() => setHovered(false)}
          onFocus={() => {
            resumed.current = true;
            setFocused(true);
          }}
          onBlur={() => setFocused(false)}
        >
          <span className={classes.idle} aria-hidden title={feed.isError ? t('offline') : undefined}>
            <span className={classes.liveDot} />
            <span className={classes.idleLabel}>{t('idle')}</span>
          </span>
          {shown && content && (
            <button
              type="button"
              className={classes.event}
              inert={!open}
              aria-label={content.announcement}
              onClick={() => {
                dispatch({ type: 'close' });
                void navigate(content.target);
              }}
            >
              <span key={shown.id} className={classes.content}>
                <span className={classes.icon}>{content.icon}</span>
                <span className={classes.text}>
                  <span className={classes.title}>{content.title}</span>
                  <span className={classes.detail}>
                    <span className={classes.detailText}>{content.detail}</span>
                    {shown.is_demo === true && <span className={classes.demo}>{tc('demo.badge')}</span>}
                  </span>
                </span>
                {shown.kind === 'score_changed' && <ScoreShift event={shown} instant={reduced} />}
              </span>
            </button>
          )}
        </div>
      )}
    </div>
  );
}
