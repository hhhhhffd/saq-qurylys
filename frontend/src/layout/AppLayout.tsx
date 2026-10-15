import { Suspense } from 'react';
import { NavLink, Outlet } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth/useAuth';
import { LoadingBlock } from '@/components/QueryState';
import { ActivityIsland } from './ActivityIsland';
import { LanguageSwitch } from './LanguageSwitch';
import { NotificationsBell } from './NotificationsBell';
import { UserMenu } from './UserMenu';
import classes from './AppLayout.module.css';

export function AppLayout() {
  const { t } = useTranslation();
  const { canSeeRegistry, isAdmin } = useAuth();

  const tabs = [
    ...(canSeeRegistry
      ? [
          { to: '/map', label: t('nav.map') },
          { to: '/objects', label: t('nav.objects') },
          { to: '/ads', label: t('nav.ads') },
        ]
      : []),
    { to: '/signals', label: t('nav.signals') },
    ...(isAdmin ? [{ to: '/admin', label: t('nav.admin') }] : []),
  ];

  return (
    <div className={classes.shell}>
      <header className={classes.header}>
        <div className={classes.bar}>
          <NavLink to="/" className={classes.wordmark} aria-label={t('appName')}>
            SAQ <span>QURYLYS</span>
          </NavLink>
          <nav className={classes.nav} aria-label={t('header.menu')}>
            {tabs.map((tab) => (
              <NavLink
                key={tab.to}
                to={tab.to}
                className={({ isActive }) => `${classes.tab} ${isActive ? classes.active : ''}`}
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
          {canSeeRegistry && <ActivityIsland />}
          <div className={classes.tools}>
            <LanguageSwitch />
            <NotificationsBell />
            <UserMenu />
          </div>
        </div>
      </header>
      <main className={classes.main}>
        <Suspense fallback={<LoadingBlock />}>
          <div className="page-enter">
            <Outlet />
          </div>
        </Suspense>
      </main>
    </div>
  );
}
