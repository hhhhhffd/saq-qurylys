import type { ComponentType } from 'react';
import { Navigate, NavLink, useParams } from 'react-router';
import { useTranslation } from 'react-i18next';
import { PageHeader } from '@/components/PageHeader';
import { FactorsSection } from './FactorsSection';
import { HolidaysSection } from './HolidaysSection';
import { PhrasesSection } from './PhrasesSection';
import { RegistrySection } from './RegistrySection';
import { SettingsSection } from './SettingsSection';
import { TerritoriesSection } from './TerritoriesSection';
import { UsersSection } from './UsersSection';
import { ADMIN_SECTIONS, DEFAULT_SECTION, isAdminSection, type AdminSection } from './sections';
import classes from './AdminPage.module.css';

const SECTION_VIEWS: Record<AdminSection, ComponentType> = {
  users: UsersSection,
  factors: FactorsSection,
  phrases: PhrasesSection,
  holidays: HolidaysSection,
  settings: SettingsSection,
  territories: TerritoriesSection,
  registry: RegistrySection,
};

export function AdminPage() {
  const { t } = useTranslation('admin');
  const { section } = useParams();

  if (!isAdminSection(section)) return <Navigate to={`/admin/${DEFAULT_SECTION}`} replace />;
  const SectionView = SECTION_VIEWS[section];

  return (
    <>
      <PageHeader title={t('title')} subtitle={t('subtitle')} />
      <nav className={classes.nav} aria-label={t('sectionsLabel')}>
        {ADMIN_SECTIONS.map((item) => (
          <NavLink
            key={item}
            to={`/admin/${item}`}
            className={({ isActive }) => `${classes.tab} ${isActive ? classes.active : ''}`}
          >
            {t(`sections.${item}`)}
          </NavLink>
        ))}
      </nav>
      <SectionView />
    </>
  );
}
