import { IconLogout } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth/useAuth';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useEnum } from '@/i18n/useEnum';

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('');
}

export function UserMenu() {
  const { t } = useTranslation();
  const e = useEnum();
  const { user, logout } = useAuth();
  if (!user) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={t('header.userMenu')}
          className="grid h-11 min-w-11 place-items-center rounded-[2px] text-text-2 outline-none transition-colors hover:bg-hover hover:text-text active:bg-pressed aria-expanded:bg-hover focus-visible:ring-2 focus-visible:ring-focus"
        >
          <Avatar>
            <AvatarFallback>{initials(user.full_name || user.username)}</AvatarFallback>
          </Avatar>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="flex flex-col gap-0.5">
          <span className="truncate text-sm font-semibold tracking-normal text-text normal-case">{user.full_name || user.username}</span>
          <span className="text-xs font-normal tracking-normal text-text-3 normal-case">{e('role', user.role)}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={logout}>
          <IconLogout />
          {t('auth.logout')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
