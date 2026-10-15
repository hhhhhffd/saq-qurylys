import { clsx, type ClassValue } from 'clsx';
import { extendTailwindMerge } from 'tailwind-merge';

// tailwind-merge knows Tailwind's own scales only; the theme's extra sizes and shadows would be taken for colors
// (`text-2xs` would be dropped by a later `text-text-2`), so they are declared here.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      'font-size': [{ text: ['3xs', '2xs'] }],
      shadow: [{ shadow: ['1', '2', 'glow', 'window'] }],
    },
  },
});

/** Joins class names and resolves Tailwind conflicts: the last one wins. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
