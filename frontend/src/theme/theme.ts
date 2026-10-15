import { createTheme, type CSSVariablesResolver, type MantineColorsTuple } from '@mantine/core';

/*
 * Mantine stays only for screens that are not migrated to Tailwind/shadcn yet (docs/UI.md §7). It is forced dark and
 * its palettes mirror tokens.css: index 6 is the base color of a token, so `filled` variants use the token itself.
 * Phase C deletes this file together with `@mantine/*`.
 */
const brand: MantineColorsTuple = [
  '#ffe8f0', '#ffc9dc', '#ffa3c4', '#ff7aa8', '#ff5c93', '#ff2d75', '#f0035b', '#d10250', '#a80241', '#7a0130',
];
// Neutral indigo greys: text, borders and surfaces of the theme.
const ink: MantineColorsTuple = [
  '#ebe8fd', '#d4d1ec', '#b5b3c9', '#9d98c0', '#8d87b8', '#6f6a99', '#5f597d', '#3a3170', '#2a2350', '#1a1535',
];
const gray: MantineColorsTuple = [
  '#ebe8fd', '#d4d1ec', '#b5b3c9', '#9d98c0', '#8d87b8', '#7d7899', '#6f6a99', '#5f597d', '#3a3170', '#2a2350',
];
const dark: MantineColorsTuple = [
  '#ebe8fd', '#d4d1ec', '#b5b3c9', '#8d87b8', '#3a3170', '#2a2350', '#221c42', '#0f0c20', '#0b091a', '#07050f',
];
const red: MantineColorsTuple = [
  '#ffe9e6', '#ffcfc9', '#ffb0a6', '#ff8a7d', '#ff6a5b', '#ff5748', '#ff4d3d', '#d9382a', '#b02a1e', '#841f16',
];
const green: MantineColorsTuple = [
  '#e3faee', '#c3f2d9', '#9febbf', '#7ee8ad', '#5adc95', '#44d587', '#34d17b', '#27a862', '#1d804a', '#145a33',
];
const yellow: MantineColorsTuple = [
  '#fff6df', '#ffeabc', '#ffdd93', '#ffd27a', '#fbc55a', '#f8bd47', '#f5b83d', '#cc9529', '#9b6f16', '#6e4d0b',
];
// Tooltips and other floating hints sit on the raised surface.
const raised: MantineColorsTuple = [
  '#ebe8fd', '#d4d1ec', '#b5b3c9', '#8d87b8', '#3a3170', '#2a2350', '#221c42', '#1a1535', '#110f24', '#0f0c20',
];

export const theme = createTheme({
  primaryColor: 'brand',
  primaryShade: 6,
  autoContrast: true,
  colors: { brand, ink, gray, dark, red, green, yellow, raised },
  white: '#ffffff',
  black: '#0f0c20',
  fontFamily: "'Tektur Variable', system-ui, sans-serif",
  fontFamilyMonospace: "ui-monospace, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace",
  headings: { fontFamily: 'inherit', fontWeight: '600' },
  fontSizes: { xs: '0.75rem', sm: '0.8125rem', md: '0.875rem', lg: '1rem', xl: '1.125rem' },
  lineHeights: { xs: '1.4', sm: '1.45', md: '1.5', lg: '1.5', xl: '1.5' },
  radius: { xs: '2px', sm: '2px', md: '4px', lg: '6px', xl: '6px' },
  defaultRadius: 'md',
  shadows: {
    xs: '0 0 0 1px rgba(0,0,0,0.2)',
    sm: '0 4px 12px rgba(0,0,0,0.35)',
    md: '0 12px 40px rgba(0,0,0,0.45)',
    lg: '0 12px 40px rgba(0,0,0,0.5)',
    xl: '0 0 80px -24px rgba(240,3,91,0.45)',
  },
  cursorType: 'pointer',
  respectReducedMotion: true,
  components: {
    Button: { defaultProps: { size: 'sm', fw: 500 } },
    ActionIcon: { defaultProps: { variant: 'subtle', color: 'gray' } },
    Badge: { defaultProps: { variant: 'light' } },
    Modal: {
      defaultProps: {
        radius: 'md',
        centered: true,
        overlayProps: { backgroundOpacity: 0.72, blur: 4, color: '#05030c' },
        shadow: 'xl',
      },
    },
    Drawer: {
      defaultProps: { overlayProps: { backgroundOpacity: 0.72, blur: 4, color: '#05030c' }, shadow: 'xl' },
    },
    Paper: { defaultProps: { radius: 'md' } },
    Popover: { defaultProps: { shadow: 'md', radius: 'md' } },
    Menu: { defaultProps: { shadow: 'md', radius: 'md' } },
    Select: { defaultProps: { comboboxProps: { shadow: 'md' } } },
    Tooltip: { defaultProps: { color: 'raised', withArrow: false, openDelay: 250 } },
    Table: { defaultProps: { verticalSpacing: 6, horizontalSpacing: 'sm' } },
    Loader: { defaultProps: { type: 'dots', color: 'gray' } },
  },
});

/** Tonal variants (`light`, `subtle`, `outline`) of the zone colors read the zone tokens, not Mantine's own tints. */
function zoneVariables(name: 'red' | 'green' | 'yellow', zone: string) {
  return {
    [`--mantine-color-${name}-light`]: `var(--zone-${zone}-bg)`,
    [`--mantine-color-${name}-light-hover`]: `color-mix(in srgb, var(--zone-${zone}) 22%, transparent)`,
    [`--mantine-color-${name}-light-color`]: `var(--zone-${zone}-ink)`,
    [`--mantine-color-${name}-outline`]: `var(--zone-${zone}-ink)`,
    [`--mantine-color-${name}-outline-hover`]: `var(--zone-${zone}-bg)`,
    [`--mantine-color-${name}-text`]: `var(--zone-${zone}-ink)`,
  };
}

export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {
    '--mantine-color-brand-filled': 'var(--accent)',
    '--mantine-color-brand-filled-hover': 'var(--accent-hover)',
    '--mantine-color-brand-light': 'color-mix(in srgb, var(--accent) 16%, transparent)',
    '--mantine-color-brand-light-hover': 'color-mix(in srgb, var(--accent) 24%, transparent)',
    '--mantine-color-brand-light-color': 'var(--accent-text)',
    '--mantine-color-brand-outline': 'var(--accent-text)',
    '--mantine-color-brand-outline-hover': 'color-mix(in srgb, var(--accent) 16%, transparent)',
    '--mantine-color-brand-text': 'var(--accent-text)',
    '--mantine-color-red-filled': 'var(--zone-red)',
    '--mantine-color-red-filled-hover': 'color-mix(in srgb, var(--zone-red) 86%, white)',
    '--mantine-color-green-filled': 'var(--zone-green)',
    '--mantine-color-green-filled-hover': 'color-mix(in srgb, var(--zone-green) 86%, white)',
    '--mantine-color-yellow-filled': 'var(--zone-yellow)',
    '--mantine-color-yellow-filled-hover': 'color-mix(in srgb, var(--zone-yellow) 86%, white)',
    '--mantine-color-gray-light': 'var(--zone-none-bg)',
    '--mantine-color-gray-light-hover': 'var(--pressed)',
    '--mantine-color-gray-light-color': 'var(--text-2)',
    '--mantine-color-gray-outline': 'var(--text-2)',
    '--mantine-color-gray-outline-hover': 'var(--hover)',
    '--mantine-color-gray-text': 'var(--text-2)',
    '--mantine-color-ink-light': 'var(--zone-none-bg)',
    '--mantine-color-ink-light-hover': 'var(--pressed)',
    '--mantine-color-ink-light-color': 'var(--text-2)',
    '--mantine-color-ink-text': 'var(--text-2)',
  },
  light: {},
  dark: {
    '--mantine-color-body': 'var(--bg)',
    '--mantine-color-text': 'var(--text)',
    '--mantine-color-dimmed': 'var(--text-2)',
    '--mantine-color-anchor': 'var(--link)',
    '--mantine-color-placeholder': 'var(--text-3)',
    '--mantine-color-default': 'var(--surface-sunken)',
    '--mantine-color-default-hover': 'var(--surface-raised)',
    '--mantine-color-default-border': 'var(--border-strong)',
    '--mantine-color-default-color': 'var(--text)',
    '--mantine-color-error': 'var(--zone-red)',
    '--mantine-color-disabled': 'var(--hover)',
    '--mantine-color-disabled-color': 'var(--text-disabled)',
    '--mantine-color-disabled-border': 'var(--border)',
    ...zoneVariables('red', 'red'),
    ...zoneVariables('green', 'green'),
    ...zoneVariables('yellow', 'yellow'),
  },
});
