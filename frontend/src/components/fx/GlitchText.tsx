/*
 * GlitchText
 * Source: https://reactbits.dev (React Bits, Copyright (c) 2026 David Haz, MIT + Commons Clause), see THIRD_PARTY_NOTICES.md.
 * Adapted for this project: pink and violet shadows from the tokens instead of red and cyan, background from a token,
 * offsets in em so it scales with the text, `cn` so `className` overrides win, still under reduced motion.
 * The `glitch` keyframes and the `animate-glitch-*` utilities live in src/theme/app.css.
 */
import { type CSSProperties } from 'react';
import { cn } from '@/lib/utils';

interface GlitchTextProps {
  children: string;
  /** seconds per cycle factor: lower is faster */
  speed?: number;
  enableShadows?: boolean;
  /** glitch only while hovered */
  enableOnHover?: boolean;
  /** colors of the left and right shadow: brand pink and the palette's violet by default */
  shadowColors?: [string, string];
  /**
   * The glitch layers hide a copy of the text, so they need an opaque fill that matches what is behind the text.
   * `transparent` suits text over an Aurora or any image.
   */
  backgroundColor?: string;
  className?: string;
}

export default function GlitchText({
  children,
  speed = 0.5,
  enableShadows = true,
  enableOnHover = false,
  shadowColors = ['var(--accent)', 'var(--graph-developer)'],
  backgroundColor = 'var(--bg)',
  className,
}: GlitchTextProps) {
  const style = {
    '--after-duration': `${speed * 3}s`,
    '--before-duration': `${speed * 2}s`,
    '--after-shadow': enableShadows ? `-0.04em 0 ${shadowColors[0]}` : 'none',
    '--before-shadow': enableShadows ? `0.04em 0 ${shadowColors[1]}` : 'none',
    '--glitch-bg': backgroundColor,
  } as CSSProperties;

  const layers =
    'after:absolute after:top-0 after:left-[0.06em] after:overflow-hidden after:bg-(--glitch-bg) after:text-text after:[clip-path:inset(0_0_0_0)] ' +
    'before:absolute before:top-0 before:left-[-0.06em] before:overflow-hidden before:bg-(--glitch-bg) before:text-text before:[clip-path:inset(0_0_0_0)] ' +
    // Under reduced motion the layers go away and the text is static.
    'motion-reduce:after:hidden motion-reduce:before:hidden';

  const always =
    'after:content-[attr(data-text)] after:[text-shadow:var(--after-shadow)] after:animate-glitch-after ' +
    'before:content-[attr(data-text)] before:[text-shadow:var(--before-shadow)] before:animate-glitch-before';

  const onHover =
    "after:content-[''] after:opacity-0 before:content-[''] before:opacity-0 " +
    'hover:after:content-[attr(data-text)] hover:after:opacity-100 hover:after:[text-shadow:var(--after-shadow)] hover:after:animate-glitch-after ' +
    'hover:before:content-[attr(data-text)] hover:before:opacity-100 hover:before:[text-shadow:var(--before-shadow)] hover:before:animate-glitch-before';

  return (
    <div
      style={style}
      data-text={children}
      className={cn('relative inline-block text-[clamp(2rem,10vw,8rem)] font-black whitespace-nowrap text-text select-none', layers, enableOnHover ? onHover : always, className)}
    >
      {children}
    </div>
  );
}
