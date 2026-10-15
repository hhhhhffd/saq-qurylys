/*
 * Spotlight: a soft pink light cone falling from the top of its container; it fades in once on mount. Our own
 * implementation. Place it as the first child of a `relative` container; it never takes pointer events. With
 * prefers-reduced-motion it simply is there, without the fade.
 */
import type { CSSProperties, ComponentProps } from 'react';
import { cn } from '@/lib/utils';

interface SpotlightProps extends ComponentProps<'div'> {
  /** color of the light: a token or any CSS color */
  color?: string;
}

export function Spotlight({ className, color = 'var(--accent)', style, ...props }: SpotlightProps) {
  const tint = (percent: number) => `color-mix(in srgb, ${color} ${percent}%, transparent)`;
  const fade = 'linear-gradient(to bottom, #000 0%, rgba(0,0,0,0.55) 45%, transparent 90%)';
  return (
    <div
      aria-hidden
      data-slot="spotlight"
      className={cn('pointer-events-none absolute inset-x-0 top-0 h-[75%] overflow-hidden animate-spotlight motion-reduce:animate-none', className)}
      style={style}
      {...props}
    >
      {/* the cone: from a point above the container, opening downwards */}
      <div
        className="absolute -top-[6%] left-1/2 h-[130%] w-[min(1100px,140%)] -translate-x-1/2 blur-2xl"
        style={
          {
            background: `conic-gradient(from 148deg at 50% 0%, transparent 0deg, ${tint(40)} 20deg, ${tint(62)} 32deg, ${tint(40)} 44deg, transparent 64deg, transparent 360deg)`,
            maskImage: fade,
            WebkitMaskImage: fade,
          } as CSSProperties
        }
      />
      {/* the lamp: a glow where the light comes from */}
      <div
        className="absolute -top-[18%] left-1/2 h-[60%] w-[min(560px,70%)] -translate-x-1/2 blur-3xl"
        style={{ background: `radial-gradient(closest-side, ${tint(55)}, transparent)` }}
      />
    </div>
  );
}
