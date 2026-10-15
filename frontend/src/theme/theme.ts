import { createTheme, type CSSVariablesResolver, type MantineColorsTuple } from '@mantine/core';

// Palettes mirror the tokens in tokens.css so Mantine components that pick
// "red"/"green"/"yellow" stay inside the same muted family.
const ink: MantineColorsTuple = [
  '#f1f1ee', '#e6e6e3', '#d4d4d0', '#bdbdb8', '#9a9a96', '#7a7a76', '#5c5c5a', '#444446', '#2c2c2e', '#1d1d1f',
];
const gray: MantineColorsTuple = [
  '#f6f6f3', '#ededea', '#e1e1dd', '#d2d2cd', '#b9b9b4', '#9a9a95', '#7a7a76', '#5c5c5a', '#444446', '#2c2c2e',
];
const red: MantineColorsTuple = [
  '#f7eceb', '#efd7d4', '#e4b9b4', '#d89790', '#cd766d', '#c6615a', '#c2453d', '#a53a33', '#8e2a24', '#6e1f1b',
];
const green: MantineColorsTuple = [
  '#eaf3ec', '#d3e6d8', '#b2d3bb', '#8dbd9b', '#6ba97f', '#529a6a', '#3f8f5b', '#33774a', '#245c39', '#19432a',
];
const yellow: MantineColorsTuple = [
  '#fbf3df', '#f5e6bc', '#edd38c', '#e4c063', '#dcae3f', '#d7a12c', '#d49a1f', '#b07f16', '#7a5608', '#5a3f05',
];

export const theme = createTheme({
  primaryColor: 'ink',
  primaryShade: 8,
  autoContrast: true,
  colors: { ink, gray, red, green, yellow },
  white: '#f6f6f3',
  black: '#1d1d1f',
  fontFamily:
    "-apple-system, BlinkMacSystemFont, 'SF Pro Text', 'SF Pro Display', Inter, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif",
  fontFamilyMonospace: "ui-monospace, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace",
  headings: { fontFamily: 'inherit', fontWeight: '620' },
  fontSizes: { xs: '0.75rem', sm: '0.8125rem', md: '0.875rem', lg: '1rem', xl: '1.125rem' },
  lineHeights: { xs: '1.4', sm: '1.45', md: '1.5', lg: '1.5', xl: '1.5' },
  radius: { xs: '4px', sm: '6px', md: '8px', lg: '12px', xl: '16px' },
  defaultRadius: 'md',
  shadows: {
    xs: '0 1px 2px rgba(28,28,30,0.05)',
    sm: '0 1px 3px rgba(28,28,30,0.08)',
    md: '0 8px 28px rgba(28,28,30,0.14)',
    lg: '0 12px 36px rgba(28,28,30,0.16)',
    xl: '0 16px 48px rgba(28,28,30,0.2)',
  },
  cursorType: 'pointer',
  respectReducedMotion: true,
  components: {
    Button: { defaultProps: { size: 'sm', fw: 500 } },
    ActionIcon: { defaultProps: { variant: 'subtle', color: 'gray' } },
    Badge: { defaultProps: { variant: 'light' } },
    Modal: {
      defaultProps: {
        radius: 'lg',
        centered: true,
        overlayProps: { backgroundOpacity: 0.38, blur: 4, color: '#1d1d1f' },
        shadow: 'xl',
      },
    },
    Drawer: {
      defaultProps: { overlayProps: { backgroundOpacity: 0.38, blur: 4, color: '#1d1d1f' }, shadow: 'xl' },
    },
    Paper: { defaultProps: { radius: 'lg' } },
    Popover: { defaultProps: { shadow: 'md', radius: 'md' } },
    Menu: { defaultProps: { shadow: 'md', radius: 'md' } },
    Select: { defaultProps: { comboboxProps: { shadow: 'md' } } },
    Tooltip: { defaultProps: { color: 'ink', withArrow: false, openDelay: 250 } },
    Table: { defaultProps: { verticalSpacing: 6, horizontalSpacing: 'sm' } },
    Loader: { defaultProps: { type: 'dots', color: 'gray' } },
  },
});

export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {},
  light: {
    '--mantine-color-body': 'var(--bg)',
    '--mantine-color-text': 'var(--text)',
    '--mantine-color-dimmed': 'var(--text-2)',
    '--mantine-color-anchor': 'var(--link)',
    '--mantine-color-default': 'var(--surface-raised)',
    '--mantine-color-default-hover': 'var(--hover)',
    '--mantine-color-default-border': 'var(--border-strong)',
    '--mantine-color-default-color': 'var(--text)',
    '--mantine-color-error': 'var(--zone-red)',
  },
  dark: {},
});
