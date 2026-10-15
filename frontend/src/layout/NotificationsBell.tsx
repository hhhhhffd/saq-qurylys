import { ActionIcon, Badge, Button, Indicator, Popover, ScrollArea, Text } from '@mantine/core';
import { IconBell } from '@tabler/icons-react';
import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications } from '@/api/hooks/misc';
import type { AppNotification } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';
import classes from './NotificationsBell.module.css';

/** Where a notification leads, by the entity it references. */
function targetPath(notification: AppNotification): string | null {
  const { entity_type: type, entity_id: id } = notification;
  if (id == null) return null;
  switch (type) {
    case 'signal_card':
    case 'signal':
      return `/signals/${id}`;
    case 'object':
    case 'construction_object':
      return `/objects/${id}`;
    case 'ad_post':
    case 'ad':
      return `/ads?ad=${id}`;
    default:
      return null;
  }
}

function subjectOf(notification: AppNotification): string | null {
  const payload = notification.payload ?? {};
  const value = payload.number ?? payload.object_name ?? payload.name;
  return typeof value === 'string' ? value : null;
}

export function NotificationsBell() {
  const { t } = useTranslation();
  const e = useEnum();
  const { dateTime } = useFormat();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { data = [] } = useNotifications(user !== null);
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllNotificationsRead();

  const open = (notification: AppNotification) => {
    markRead.mutate(notification.id);
    const path = targetPath(notification);
    if (path) void navigate(path);
  };

  return (
    <Popover position="bottom-end" width={360} withinPortal>
      <Popover.Target>
        <Indicator label={data.length > 99 ? '99+' : data.length} disabled={data.length === 0} size={16} color="red" offset={5}>
          <ActionIcon aria-label={t('header.notifications')} size="lg" radius="xl">
            <IconBell size={20} stroke={1.6} />
          </ActionIcon>
        </Indicator>
      </Popover.Target>
      <Popover.Dropdown p={0}>
        <div className={classes.head}>
          <Text fw={600} size="sm">
            {t('header.notifications')}
          </Text>
          {data.length > 0 && (
            <Button variant="subtle" size="compact-xs" onClick={() => markAll.mutate()} loading={markAll.isPending}>
              {t('header.markAllRead')}
            </Button>
          )}
        </div>
        {data.length === 0 ? (
          <Text size="sm" c="dimmed" ta="center" py="lg">
            {t('header.noNotifications')}
          </Text>
        ) : (
          <ScrollArea.Autosize mah={420}>
            <ul className={classes.list}>
              {data.map((notification) => (
                <li key={notification.id}>
                  <button type="button" className={classes.item} onClick={() => open(notification)}>
                    <span className={classes.title}>{e('notification_kind', notification.kind)}</span>
                    {subjectOf(notification) && <Badge variant="default" size="sm">{subjectOf(notification)}</Badge>}
                    <span className={`${classes.time} tnum`}>{dateTime(notification.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </ScrollArea.Autosize>
        )}
      </Popover.Dropdown>
    </Popover>
  );
}
