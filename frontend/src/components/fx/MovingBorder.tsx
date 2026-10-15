/*
 * MovingBorder: a bright small glow dot running along the border of what it wraps (a button). Our own implementation.
 *
 * The dot follows `offset-path: rect()` around the wrapper, so it moves at an even speed on any size. Where the browser
 * lacks `rect()` in offset-path, the dot is not shown and only the border stays. It stops while off-screen, and with
 * prefers-reduced-motion the border is a static pink line.
 */
import { useEffect, useRef, useState, type CSSProperties, type ComponentProps } from 'react';
import { useReducedMotion } from '@/lib/hooks';
import { cn } from '@/lib/utils';

interface MovingBorderProps extends ComponentProps<'span'> {
  /** seconds per lap */
  duration?: number;
  /** color of the dot's halo: a token or any CSS color */
  color?: string;
}

/** `<MovingBorder><Button>…</Button></MovingBorder>`: the child should have the same radius as `className` rounds to. */
export function MovingBorder({ className, children, duration = 3.2, color = 'var(--accent)', style, ...props }: MovingBorderProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const reduced = useReducedMotion();
  const [onScreen, setOnScreen] = useState(true);

  useEffect(() => {
    const el = ref.current;
    if (!el || reduced) return;
    const observer = new IntersectionObserver((entries) => setOnScreen(entries.some((entry) => entry.isIntersecting)));
    observer.observe(el);
    return () => observer.disconnect();
  }, [reduced]);

  return (
    <span
      ref={ref}
      data-slot="moving-border"
      // The wrapper's 1px padding is the border line; the child sits inside it.
      className={cn('relative inline-flex rounded p-px', reduced ? 'bg-primary/60' : 'bg-border-strong', className)}
      style={{ '--moving-border-duration': `${duration}s`, ...style } as CSSProperties}
      {...props}
    >
      {!reduced && (
        <span
          aria-hidden
          className="pointer-events-none absolute top-0 left-0 hidden h-[3px] w-6 animate-moving-border rounded-full supports-[offset-path:rect(auto_auto_auto_auto)]:block"
          style={{
            offsetPath: 'rect(auto auto auto auto round 4px)',
            offsetRotate: 'auto',
            offsetAnchor: '50% 50%',
            background: 'linear-gradient(to right, transparent, white)',
            boxShadow: `0 0 6px 1px ${color}, 0 0 14px 2px color-mix(in srgb, ${color} 55%, transparent)`,
            animationPlayState: onScreen ? 'running' : 'paused',
          }}
        />
      )}
      {children}
    </span>
  );
}
