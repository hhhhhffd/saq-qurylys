export const ADMIN_SECTIONS = [
  'users',
  'factors',
  'phrases',
  'holidays',
  'settings',
  'territories',
  'registry',
] as const;

export type AdminSection = (typeof ADMIN_SECTIONS)[number];

export const DEFAULT_SECTION: AdminSection = 'users';

export function isAdminSection(value: string | undefined): value is AdminSection {
  return ADMIN_SECTIONS.some((section) => section === value);
}
