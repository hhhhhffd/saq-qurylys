import type { ComponentType } from 'react';
import {
  IconAdjustmentsHorizontal,
  IconBook2,
  IconCalendarEvent,
  IconDatabaseImport,
  IconMap2,
  IconSettings,
  IconUsers,
  type Icon,
} from '@tabler/icons-react';
import { Navigate, NavLink, useParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { PageHeader } from '@/components/PageHeader';
import { cn } from '@/lib/utils';
import { FactorsSection } from './FactorsSection';
import { HolidaysSection } from './HolidaysSection';
import { PhrasesSection } from './PhrasesSection';
import { RegistrySection } from './RegistrySection';
import { SettingsSection } from './SettingsSection';
import { TerritoriesSection } from './TerritoriesSection';
import { UsersSection } from './UsersSection';
import { ADMIN_SECTIONS, DEFAULT_SECTION, isAdminSection, type AdminSection } from './sections';

const SECTION_VIEWS: Record<AdminSection, ComponentType> = {
  users: UsersSection,
  factors: FactorsSection,
  phrases: PhrasesSection,
  holidays: HolidaysSection,
  settings: SettingsSection,
  territories: TerritoriesSection,
  registry: RegistrySection,
};

const SECTION_ICONS: Record<AdminSection, Icon> = {
  users: IconUsers,
  factors: IconAdjustmentsHorizontal,
  phrases: IconBook2,
  holidays: IconCalendarEvent,
  settings: IconSettings,
  territories: IconMap2,
  registry: IconDatabaseImport,
};

export function AdminPage() {
  const { t } = useTranslation('admin');
  const { section } = useParams();

  if (!isAdminSection(section)) return <Navigate to={`/admin/${DEFAULT_SECTION}`} replace />;
  const SectionView = SECTION_VIEWS[section];

  return (
    <>
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <nav
        className="mb-5 flex gap-5 overflow-x-auto border-b border-border [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        aria-label={t('sectionsLabel')}
      >
        {ADMIN_SECTIONS.map((item) => {
          const SectionIcon = SECTION_ICONS[item];
          return (
            <NavLink
              key={item}
              to={`/admin/${item}`}
              className={({ isActive }) =>
                cn(
                  '-mb-px inline-flex h-9 flex-none items-center gap-1.5 border-b-2 border-transparent font-heading text-xs font-semibold tracking-wider whitespace-nowrap text-text-3 uppercase transition-colors duration-(--dur) outline-none hover:text-text focus-visible:ring-1 focus-visible:ring-focus',
                  isActive && 'border-primary text-accent-text hover:text-accent-text',
                )
              }
            >
              <SectionIcon className="size-4" aria-hidden />
              {t(`sections.${item}`)}
            </NavLink>
          );
        })}
      </nav>
      <SectionView />
    </>
  );
}
