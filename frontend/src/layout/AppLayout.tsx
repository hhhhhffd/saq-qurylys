import { Suspense } from 'react';
import { NavLink, Outlet } from 'react-router';
import { IconBuildingSkyscraper, IconMap2, IconSend, IconSettings, IconSpeakerphone, IconTopologyStar3 } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth/useAuth';
import { LoadingBlock } from '@/components/QueryState';
import { ActivityIsland } from './ActivityIsland';
import { LanguageSwitch } from './LanguageSwitch';
import { NotificationsBell } from './NotificationsBell';
import { UserMenu } from './UserMenu';

const tabClass =
  'group flex h-12 flex-none items-center gap-1.5 px-3 font-heading text-xs font-semibold tracking-wider whitespace-nowrap text-text-3 uppercase no-underline outline-none ' +
  'transition-colors duration-(--dur) hover:text-text-2 focus-visible:text-text-2 aria-[current=page]:text-accent-text ' +
  'aria-[current=page]:[text-shadow:0_0_14px_var(--accent-glow)] [&_svg]:size-4 [&_svg]:shrink-0';

export function AppLayout() {
  const { t } = useTranslation();
  const { canSeeRegistry, isAdmin } = useAuth();

  const tabs = [
    ...(canSeeRegistry
      ? [
          { to: '/map', label: t('nav.map'), icon: <IconMap2 /> },
          { to: '/objects', label: t('nav.objects'), icon: <IconBuildingSkyscraper /> },
          { to: '/ads', label: t('nav.ads'), icon: <IconSpeakerphone /> },
          { to: '/graph', label: t('nav.graph'), icon: <IconTopologyStar3 /> },
        ]
      : []),
    { to: '/signals', label: t('nav.signals'), icon: <IconSend /> },
    ...(isAdmin ? [{ to: '/admin', label: t('nav.admin'), icon: <IconSettings /> }] : []),
  ];

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-40 border-b border-border bg-surface-raised">
        <div className="mx-auto flex min-h-12 max-w-(--page-max) items-center gap-6 px-(--gutter) max-[62em]:flex-wrap max-[62em]:gap-x-3 max-[62em]:gap-y-0">
          <NavLink
            to="/"
            aria-label={t('appName')}
            className="flex-none font-heading text-sm font-bold tracking-widest whitespace-nowrap text-text no-underline"
          >
            SAQ <span className="text-accent-text [text-shadow:0_0_14px_var(--accent-glow)]">QURYLYS</span>
          </NavLink>
          <nav
            className="-mx-3 flex min-w-0 items-center overflow-x-auto [scrollbar-width:none] max-[62em]:order-3 max-[62em]:mx-0 max-[62em]:basis-full [&::-webkit-scrollbar]:hidden"
            aria-label={t('header.menu')}
          >
            {tabs.map((tab) => (
              <NavLink key={tab.to} to={tab.to} className={tabClass}>
                {tab.icon}
                {tab.label}
              </NavLink>
            ))}
          </nav>
          {canSeeRegistry && <ActivityIsland />}
          <div className="ml-auto flex flex-none items-center gap-2">
            <LanguageSwitch />
            <NotificationsBell />
            <UserMenu />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-(--page-max) px-(--gutter) pt-6 pb-14">
        <Suspense fallback={<LoadingBlock />}>
          <div className="animate-in duration-200 fade-in-0 slide-in-from-bottom-1">
            <Outlet />
          </div>
        </Suspense>
      </main>
    </div>
  );
}
