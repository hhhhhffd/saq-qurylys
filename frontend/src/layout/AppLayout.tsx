import { Suspense } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router';
import {
  IconBuildingSkyscraper,
  IconChevronDown,
  IconDots,
  IconListCheck,
  IconMap2,
  IconRss,
  IconSend,
  IconSettings,
  IconSpeakerphone,
  IconTopologyStar3,
} from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth/useAuth';
import { LoadingBlock } from '@/components/QueryState';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ActivityIsland } from './ActivityIsland';
import { LanguageSwitch } from './LanguageSwitch';
import { NotificationsBell } from './NotificationsBell';
import { UserMenu } from './UserMenu';

const navLinkClass =
  'group flex h-12 min-h-11 flex-none items-center gap-1.5 px-3 font-heading text-xs font-semibold tracking-wider whitespace-nowrap text-text-3 uppercase no-underline outline-none ' +
  'transition-colors duration-(--dur) hover:text-text-2 focus-visible:text-text-2 focus-visible:ring-2 focus-visible:ring-focus aria-[current=page]:text-accent-text aria-[current=page]:[text-shadow:0_0_14px_var(--accent-glow)] [&_svg]:size-4 [&_svg]:shrink-0 ' +
  'max-[62em]:h-11 max-[62em]:w-full max-[62em]:min-w-0 max-[62em]:flex-col max-[62em]:justify-center max-[62em]:gap-1 max-[62em]:px-0.5 max-[62em]:py-1 max-[62em]:text-2xs max-[62em]:tracking-normal max-[62em]:leading-none';

export function AppLayout() {
  const { t } = useTranslation();
  const { canSeeRegistry, canEditRegistry, isAdmin } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const toolItems = [
    { to: '/map', label: t('nav.map'), icon: <IconMap2 />, visible: canSeeRegistry },
    { to: '/graph', label: t('nav.graph'), icon: <IconTopologyStar3 />, visible: canSeeRegistry },
    { to: '/sources', label: t('nav.sources'), icon: <IconRss />, visible: canEditRegistry },
    { to: '/admin', label: t('nav.admin'), icon: <IconSettings />, visible: isAdmin },
  ].filter((item) => item.visible);
  const activeTool = toolItems.find(
    ({ to }) => location.pathname === to || location.pathname.startsWith(`${to}/`),
  );

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-40 border-b border-border bg-surface-raised">
        <div className="mx-auto flex min-h-14 max-w-(--page-max) items-center gap-6 px-(--gutter) max-[62em]:min-h-12 max-[62em]:flex-wrap max-[62em]:gap-x-1 max-[62em]:gap-y-0">
          <Link
            to="/"
            aria-label={t('appName')}
            className="flex min-h-11 flex-none items-center font-heading text-sm font-bold tracking-widest whitespace-nowrap text-text no-underline focus-visible:ring-2 focus-visible:ring-focus max-[62em]:text-xs max-[62em]:tracking-wide"
          >
            SAQ <span className="ml-1 text-accent-text [text-shadow:0_0_14px_var(--accent-glow)]">QURYLYS</span>
          </Link>

          <nav
            className={`-mx-3 flex min-w-0 flex-1 items-center overflow-x-auto [scrollbar-width:none] max-[62em]:order-3 max-[62em]:mx-0 max-[62em]:grid max-[62em]:gap-0 max-[62em]:overflow-visible [&::-webkit-scrollbar]:hidden ${canSeeRegistry ? 'max-[62em]:basis-full max-[62em]:grid-cols-5' : 'max-[62em]:w-fit max-[62em]:flex-none max-[62em]:basis-auto max-[62em]:grid-cols-1'}`}
            aria-label={t('header.menu')}
          >
            {canSeeRegistry && (
              <NavLink to="/work" className={navLinkClass} aria-label={t('nav.work')}>
                <IconListCheck aria-hidden />
                <span className="max-[62em]:hidden">{t('nav.work')}</span>
                <span className="hidden max-[62em]:inline">{t('nav.workShort')}</span>
              </NavLink>
            )}
            {canSeeRegistry && (
              <NavLink to="/ads" className={navLinkClass} aria-label={t('nav.ads')}>
                <IconSpeakerphone aria-hidden />
                <span className="max-[62em]:hidden">{t('nav.ads')}</span>
                <span className="hidden max-[62em]:inline">{t('nav.adsShort')}</span>
              </NavLink>
            )}
            {canSeeRegistry && (
              <NavLink to="/objects" className={navLinkClass} aria-label={t('nav.objects')}>
                <IconBuildingSkyscraper aria-hidden />
                <span className="max-[62em]:hidden">{t('nav.objects')}</span>
                <span className="hidden max-[62em]:inline">{t('nav.objectsShort')}</span>
              </NavLink>
            )}
            <NavLink to="/signals" className={navLinkClass} aria-label={t('nav.cards')}>
              <IconSend aria-hidden />
              <span className="max-[62em]:hidden">{t('nav.cards')}</span>
              <span className="hidden max-[62em]:inline">{t('nav.cardsShort')}</span>
            </NavLink>

            {canSeeRegistry && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className={navLinkClass}
                    aria-label={activeTool ? t('nav.toolsCurrent', { current: activeTool.label }) : t('nav.tools')}
                    aria-current={activeTool ? 'page' : undefined}
                  >
                    <IconDots className="hidden size-4 max-[62em]:block" aria-hidden />
                    <span className="hidden max-[62em]:inline">{t('nav.more')}</span>
                    <span className="max-[62em]:hidden">
                      {t('nav.tools')}
                      {activeTool && <span className="text-text-3"> · {activeTool.label}</span>}
                    </span>
                    <IconChevronDown className="size-4 max-[62em]:hidden" aria-hidden />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="min-w-52">
                  <DropdownMenuLabel>{t('nav.tools')}</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  {toolItems.map((item) => {
                    const current = activeTool?.to === item.to;
                    return (
                      <DropdownMenuItem
                        key={item.to}
                        className="min-h-11 gap-2 font-heading text-xs font-semibold tracking-wider uppercase data-[current=true]:text-accent-text"
                        data-current={current || undefined}
                        aria-current={current ? 'page' : undefined}
                        onSelect={() => void navigate(item.to)}
                      >
                        {item.icon}
                        {item.label}
                      </DropdownMenuItem>
                    );
                  })}
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </nav>

          <div role="group" aria-label={t('header.utilities')} className="ml-auto flex flex-none items-center gap-1">
            <LanguageSwitch />
            <NotificationsBell />
            <UserMenu />
          </div>
        </div>
        {canSeeRegistry && (
          <div className="pointer-events-none absolute inset-x-0 bottom-0">
            <div className="relative mx-auto h-0 max-w-(--page-max) px-(--gutter)">
              <ActivityIsland />
            </div>
          </div>
        )}
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
