/*
 * GlowCard: a card whose border lights up with a pink conic gradient that leans towards the cursor when the cursor is
 * near the border (within `proximity` px, inside or outside); a plain border otherwise. Our own implementation.
 *
 * One shared pointer listener and one rAF loop serve every card on the page. The loop only writes two CSS variables
 * (`--glow-strength`, `--glow-angle`) on the cards, so React never re-renders while the pointer moves. Cards that are
 * off-screen are skipped. With prefers-reduced-motion the ring is not rendered at all: the border stays plain.
 */
import { useEffect, useRef, type CSSProperties, type ComponentProps } from 'react';
import { useReducedMotion } from '@/lib/hooks';
import { cn } from '@/lib/utils';

interface Tracked {
  proximity: number;
  visible: boolean;
}

const tracked = new Map<HTMLElement, Tracked>();
let pointer: { x: number; y: number } | null = null;
let frame = 0;
let visibility: IntersectionObserver | null = null;

function schedule() {
  if (!frame) frame = requestAnimationFrame(update);
}

function onPointerMove(event: PointerEvent) {
  pointer = { x: event.clientX, y: event.clientY };
  schedule();
}

function onPointerLeave() {
  pointer = null;
  schedule();
}

function update() {
  frame = 0;
  // Read all rects first, then write: no layout thrash between cards.
  const next: [HTMLElement, number, number][] = [];
  tracked.forEach((state, el) => {
    if (!state.visible) return;
    if (!pointer) {
      next.push([el, 0, 0]);
      return;
    }
    const rect = el.getBoundingClientRect();
    const outside = Math.hypot(Math.max(rect.left - pointer.x, 0, pointer.x - rect.right), Math.max(rect.top - pointer.y, 0, pointer.y - rect.bottom));
    const inside = Math.min(pointer.x - rect.left, rect.right - pointer.x, pointer.y - rect.top, rect.bottom - pointer.y);
    const distance = outside > 0 ? outside : Math.max(inside, 0);
    const strength = Math.max(0, 1 - distance / state.proximity);
    const angle = (Math.atan2(pointer.y - (rect.top + rect.height / 2), pointer.x - (rect.left + rect.width / 2)) * 180) / Math.PI + 90;
    next.push([el, strength, angle]);
  });
  next.forEach(([el, strength, angle]) => {
    el.style.setProperty('--glow-strength', strength.toFixed(3));
    el.style.setProperty('--glow-angle', `${angle.toFixed(1)}deg`);
  });
}

function track(el: HTMLElement, proximity: number) {
  if (tracked.size === 0) {
    window.addEventListener('pointermove', onPointerMove, { passive: true });
    window.addEventListener('scroll', schedule, { passive: true, capture: true });
    document.documentElement.addEventListener('pointerleave', onPointerLeave);
    visibility = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        const state = tracked.get(entry.target as HTMLElement);
        if (state) state.visible = entry.isIntersecting;
      });
      schedule();
    });
  }
  tracked.set(el, { proximity, visible: true });
  visibility?.observe(el);

  return () => {
    tracked.delete(el);
    visibility?.unobserve(el);
    el.style.setProperty('--glow-strength', '0');
    if (tracked.size === 0) {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('scroll', schedule, { capture: true });
      document.documentElement.removeEventListener('pointerleave', onPointerLeave);
      visibility?.disconnect();
      visibility = null;
      cancelAnimationFrame(frame);
      frame = 0;
    }
  };
}

// A cone of pink around the cursor's direction, seen from the card's center; the mask keeps only the 1px border.
const RING: CSSProperties = {
  background:
    'conic-gradient(from calc(var(--glow-angle) - 70deg) at 50% 50%, transparent 0deg, color-mix(in srgb, var(--accent) 45%, transparent) 35deg, var(--accent-hover) 70deg, color-mix(in srgb, var(--accent) 45%, transparent) 105deg, transparent 140deg)',
  mask: 'linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)',
  maskComposite: 'exclude',
  WebkitMask: 'linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)',
  WebkitMaskComposite: 'xor',
};

interface GlowCardProps extends ComponentProps<'div'> {
  /** how close to the border (px) the cursor must be before the glow starts */
  proximity?: number;
}

/** Panel with the cursor-following glowing border. Style it like a panel (`bg-surface` by default); `className` wins. */
export function GlowCard({ className, children, proximity = 80, style, ...props }: GlowCardProps) {
  const ref = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    if (reduced || !ref.current) return;
    return track(ref.current, proximity);
  }, [reduced, proximity]);

  return (
    <div
      ref={ref}
      data-slot="glow-card"
      className={cn('relative rounded-lg border border-border bg-surface', className)}
      style={{ '--glow-strength': 0, '--glow-angle': '0deg', ...style } as CSSProperties}
      {...props}
    >
      {!reduced && (
        <>
          <span aria-hidden className="pointer-events-none absolute -inset-[2px] rounded-[inherit] p-[4px] opacity-(--glow-strength) blur-[8px]" style={RING} />
          <span aria-hidden className="pointer-events-none absolute -inset-px rounded-[inherit] p-px opacity-(--glow-strength)" style={RING} />
        </>
      )}
      {children}
    </div>
  );
}
