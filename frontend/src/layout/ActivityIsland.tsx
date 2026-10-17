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

/** Sizes in px; the classes of the island repeat the two heights (h-8, h-12). */
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
  const reduced = useReducedMotion();

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
    <div ref={slotRef} className="pointer-events-none min-w-0 flex-[1_1_0] self-stretch max-[62em]:w-0 max-[62em]:flex-none">
      <div role="status" aria-live="polite" aria-atomic="true" data-testid="activity-live-region" className="sr-only">
        {open && content ? content.announcement : ''}
      </div>
      {geometry && (
        <div
          className={cn(
            'group pointer-events-none absolute left-1/2 h-8 w-(--w-idle) rounded-2xl bg-surface-raised shadow-[0_0_0_1px_var(--border-strong),0_6px_18px_rgba(0,0,0,0.35)]',
            'top-[calc(var(--mid)-16px)] [transform:translateX(calc(-50%_+_var(--shift-idle)))]',
            'transition-[width,height,top,transform,box-shadow] duration-[400ms] ease-[cubic-bezier(0.32,0.72,0,1)]',
            'data-[open=true]:pointer-events-auto data-[open=true]:top-[calc(var(--mid)-24px)] data-[open=true]:h-12 data-[open=true]:w-(--w-open) data-[open=true]:rounded-3xl',
            'data-[open=true]:[transform:translateX(calc(-50%_+_var(--shift-open)))] data-[open=true]:shadow-glow',
            'data-[open=true]:duration-[580ms] data-[open=true]:ease-[cubic-bezier(0.3,1.35,0.4,1)]',
            // Not enough room in the header row (narrow screens, long navigation): the open island hangs below the header.
            'data-[open=true]:data-[place=below]:top-[calc(100%+8px)]',
            'max-[62em]:hidden',
            // Entering the red zone: a red edge and a soft red glow instead of the pink one, nothing that blinks.
            'data-[alert=true]:shadow-[0_0_0_1px_color-mix(in_srgb,var(--zone-red)_62%,transparent),0_8px_28px_-6px_color-mix(in_srgb,var(--zone-red)_45%,transparent)]',
            'motion-reduce:transition-none',
          )}
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
          {/* The pill clips its content; the glow of the border (below) bleeds out of it. */}
          <div className="absolute inset-0 overflow-hidden rounded-[inherit]">
            <span
              className={cn(
                'absolute top-0 left-1/2 flex h-8 w-(--w-idle) -translate-x-1/2 items-center justify-center gap-2',
                'transition-opacity delay-[140ms] duration-[260ms] group-data-[open=true]:opacity-0 group-data-[open=true]:delay-0 group-data-[open=true]:duration-100',
              )}
              aria-hidden
              title={feed.isError ? t('offline') : undefined}
            >
              <span
                className={cn(
                  'size-1.5 flex-none animate-pulse rounded-full bg-primary shadow-[0_0_8px_var(--accent-glow)] motion-reduce:animate-none',
                  'group-data-[offline=true]:animate-none group-data-[offline=true]:bg-transparent group-data-[offline=true]:shadow-none group-data-[offline=true]:ring-[1.5px] group-data-[offline=true]:ring-text-3',
                )}
              />
              {/* Too little room for the word: the dot alone. */}
              <span className="truncate font-heading text-3xs font-semibold tracking-wider text-text-2 uppercase group-data-[compact=true]:hidden">
                {t('idle')}
              </span>
            </span>
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
                      {/* Stays whole when a long name is cut. */}
                      {shown.is_demo === true && (
                        <span className="flex-none rounded-sm border border-border-strong px-1 text-3xs font-semibold tracking-wider uppercase">
                          {tc('demo.badge')}
                        </span>
                      )}
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
