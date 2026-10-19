import { useEffect, useReducer, useRef, useState, type CSSProperties, type ReactNode } from 'react';
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
import StarBorder from '@/components/fx/StarBorder';
import { zoneColor } from '@/components/zoneColor';
import { useEnum } from '@/i18n/useEnum';
import { cn } from '@/lib/utils';
import { useReducedMotion } from '@/lib/hooks';

/** How long an event stays open; shorter when others wait, and after the pointer leaves. */
const OPEN_MS = 6000;
const OPEN_BUSY_MS = 3800;
const OPEN_RESUMED_MS = 2500;
/** Events waiting for their turn; a long absence of the tab must not turn into minutes of animation. */
const MAX_WAITING = 5;
const SCORE_DELAY_MS = 320;
const SCORE_TWEEN_MS = 760;

/** Sizes in px; the event panel class uses the same 48px height (`h-12`). */
const OPEN_WIDTH = 400;
const OPEN_HEIGHT = 48;
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
    <span className="inline-flex flex-none items-center gap-1.5 text-base font-semibold tabular-nums" aria-hidden>
      <span className="font-medium text-text-3">{from}</span>
      <IconArrowRight size={13} stroke={2} className="text-text-3" />
      <span className="min-w-[2ch] text-right text-text">{instant ? to : counted}</span>
      <span
        className="ml-1 size-2 rounded-full ring-[3px] ring-text/10 transition-colors duration-700"
        style={{ background: zoneColor(instant ? event.zone_after : zone) }}
      />
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

/** Where an event panel goes, in px relative to its zero-height anchor below the header. */
interface Geometry {
  /** vertical middle of the event anchor */
  mid: number;
  openWidth: number;
  /** horizontal offset from the center of the event anchor */
  openShift: number;
  /** whether the panel fits inside the anchor; otherwise it opens below the header */
  inBand: boolean;
}

const clamp = (value: number, min: number, max: number) =>
  min > max ? (min + max) / 2 : Math.min(Math.max(value, min), max);

/**
 * The anchor has no layout height, so event panels never reserve space in the header. Its width bounds the panel
 * and its height keeps the panel below the header instead of over the navigation or utility controls.
 */
function useGeometry() {
  const slotRef = useRef<HTMLDivElement>(null);
  const [geometry, setGeometry] = useState<Geometry | null>(null);

  useEffect(() => {
    const slot = slotRef.current;
    const anchor = slot?.offsetParent;
    if (!slot || !anchor) return;
    const measure = () => {
      const bounds = anchor.getBoundingClientRect();
      const box = slot.getBoundingClientRect();
      const left = box.left - bounds.left;
      const right = box.right - bounds.left;
      const center = bounds.width / 2;
      const openWidth = Math.min(OPEN_WIDTH, bounds.width - 2 * EDGE_GAP);
      const inBand = box.width >= openWidth && box.height >= OPEN_HEIGHT;
      setGeometry({
        mid: box.top - bounds.top + box.height / 2,
        openWidth,
        openShift: inBand ? clamp(center, left + openWidth / 2, right - openWidth / 2) - center : 0,
        inBand,
      });
    };
    // Re-measure when the event anchor changes size or moves with the responsive header.
    const observer = new ResizeObserver(measure);
    observer.observe(slot);
    observer.observe(anchor);
    return () => observer.disconnect();
  }, []);

  return { slotRef, geometry };
}

export function ActivityIsland() {
  const navigate = useNavigate();
  const present = usePresentation();
  const reduced = useReducedMotion();

  const [{ shown, open, waiting }, dispatch] = useReducer(reduce, { shown: null, open: false, waiting: [] });
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  // The pointer or focus left an open event: it gets a short grace period instead of a full one.
  const resumed = useRef(false);

  const { slotRef, geometry } = useGeometry();
  useActivityFeed((events) => dispatch({ type: 'events', events }));

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
        '--w-open': `${geometry.openWidth}px`,
        '--shift-open': `${geometry.openShift}px`,
      } as CSSProperties)
    : undefined;

  return (
    <div ref={slotRef} className="pointer-events-none min-w-0">
      <div role="status" aria-live="polite" aria-atomic="true" data-testid="activity-live-region" className="sr-only">
        {open && content ? content.announcement : ''}
      </div>
      {geometry && (
        <div
          className={cn(
            'group pointer-events-none absolute left-1/2 h-12 w-(--w-open) rounded-3xl bg-transparent opacity-0 shadow-none',
            'top-[calc(var(--mid)-24px)] [transform:translateX(calc(-50%_+_var(--shift-open)))]',
            'transition-[opacity,top,transform,box-shadow] duration-[400ms] ease-[cubic-bezier(0.32,0.72,0,1)]',
            'data-[open=true]:pointer-events-auto data-[open=true]:bg-surface-raised data-[open=true]:opacity-100 data-[open=true]:shadow-glow',
            'data-[open=true]:top-[calc(var(--mid)-24px)] data-[open=true]:h-12 data-[open=true]:w-(--w-open) data-[open=true]:rounded-3xl',
            'data-[open=true]:[transform:translateX(calc(-50%_+_var(--shift-open)))] data-[open=true]:shadow-glow',
            'data-[open=true]:duration-[580ms] data-[open=true]:ease-[cubic-bezier(0.3,1.35,0.4,1)]',
            // The event panel opens below the header, away from navigation and utility controls.
            'data-[open=true]:data-[place=below]:top-[calc(100%+8px)]',
            // Entering the red zone: a red edge and a soft red glow instead of the pink one, nothing that blinks.
            'data-[alert=true]:shadow-[0_0_0_1px_color-mix(in_srgb,var(--zone-red)_62%,transparent),0_8px_28px_-6px_color-mix(in_srgb,var(--zone-red)_45%,transparent)]',
            'motion-reduce:transition-none',
          )}
          style={style}
          data-open={open}
          data-place={geometry.inBand ? 'band' : 'below'}
          data-alert={open && content?.alert === true}
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
          {/* The pill clips its content; the glow of the border (below) bleeds out of it. */}
          <div className="absolute inset-0 overflow-hidden rounded-[inherit]">
            {shown && content && (
              <button
                type="button"
                // Laid out at the final width so the text does not reflow while the island grows; the pill clips it.
                className={cn(
                  'absolute top-0 left-1/2 m-0 h-12 w-(--w-open) -translate-x-1/2 cursor-pointer rounded-3xl border-0 bg-transparent p-0 text-left text-inherit',
                  'opacity-0 blur-[6px] transition-[opacity,filter] duration-150 ease-linear',
                  'group-data-[open=true]:opacity-100 group-data-[open=true]:blur-none group-data-[open=true]:delay-[130ms] group-data-[open=true]:duration-300',
                  'focus-visible:outline-2 focus-visible:-outline-offset-4 focus-visible:outline-focus',
                  'motion-reduce:blur-none motion-reduce:delay-0 motion-reduce:duration-200',
                )}
                inert={!open}
                aria-label={content.announcement}
                onClick={() => {
                  dispatch({ type: 'close' });
                  void navigate(content.target);
                }}
              >
                {/* Replaced when the next event takes over. */}
                <span
                  key={shown.id}
                  className="flex size-full animate-in items-center gap-2.5 py-0 pr-4 pl-2 duration-300 fade-in-0 slide-in-from-bottom-1 motion-reduce:animate-none"
                >
                  <span className="grid size-8 flex-none place-items-center rounded-full bg-primary/16 text-accent-text transition-colors duration-[400ms] group-data-[alert=true]:bg-zone-red/40 group-data-[alert=true]:text-zone-red-ink [&_svg]:size-4">
                    {content.icon}
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="truncate text-sm leading-tight font-semibold text-text">{content.title}</span>
                    <span className="flex min-w-0 items-center gap-1.5 text-xs leading-snug text-text-2">
                      <span className="truncate">{content.detail}</span>
                    </span>
                  </span>
                  {shown.kind === 'score_changed' && <ScoreShift event={shown} instant={reduced} />}
                </span>
              </button>
            )}
          </div>
          {open && (
            <StarBorder
              as="div"
              aria-hidden
              radius={24}
              duration={5}
              hover="none"
              clickPulse={false}
              backgroundColor="transparent"
              borderColor="transparent"
              color={content?.alert ? 'var(--zone-red)' : 'var(--accent)'}
              className="pointer-events-none absolute inset-0 p-0"
            />
          )}
        </div>
      )}
    </div>
  );
}
