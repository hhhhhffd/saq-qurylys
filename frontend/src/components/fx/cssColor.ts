/**
 * Canvas and WebGL code cannot read CSS variables. This turns `var(--accent)` into the token's computed color and
 * lets every other value (hex, rgb(), a color name) pass through, so the effects can take design tokens as colors.
 */
export function resolveColor(value: string): string {
  const match = /^var\((--[\w-]+)\)$/.exec(value.trim());
  if (!match) return value;
  return getComputedStyle(document.documentElement).getPropertyValue(match[1]).trim() || value;
}
