import { Avatar, Menu, Text } from '@mantine/core';
import { IconLogout } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth/useAuth';
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
    <Menu position="bottom-end" width={240} withinPortal>
      <Menu.Target>
        <button
          type="button"
          aria-label={t('header.userMenu')}
          style={{ border: 0, background: 'none', padding: 0, borderRadius: '50%' }}
        >
          <Avatar color="ink" size={30} radius="xl">
            {initials(user.full_name || user.username)}
          </Avatar>
        </button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>
          <Text size="sm" fw={600} c="var(--text)" truncate>
            {user.full_name || user.username}
          </Text>
          <Text size="xs" c="dimmed">
            {e('role', user.role)}
          </Text>
        </Menu.Label>
        <Menu.Divider />
        <Menu.Item leftSection={<IconLogout size={16} />} onClick={logout}>
          {t('auth.logout')}
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
