import { IconBell } from '@tabler/icons-react';
import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';
import { useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications } from '@/api/hooks/misc';
import type { AppNotification } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';

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
    case 'source_account':
      return '/sources';
    default:
      return null;
  }
}

/** `capture_failed` is also used when the archive copy of a sent signal card could not be saved. */
function kindOf(notification: AppNotification): string {
  const archiveFailed =
    notification.kind === 'capture_failed' &&
    (notification.entity_type === 'signal_card' || notification.payload?.reason === 'pdf_archive');
  return archiveFailed ? 'pdf_archive_failed' : notification.kind;
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
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={t('header.notifications')} className="relative">
          <IconBell />
          {data.length > 0 && (
            <Badge
              variant="default"
              className="pointer-events-none absolute -top-1 -right-1 h-4 min-w-4 rounded-full bg-primary px-1 text-primary-foreground tabular-nums"
            >
              {data.length > 99 ? '99+' : data.length}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(360px,calc(100vw-2rem))] gap-0 p-0">
        <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-1.5">
          <span className="font-heading text-2xs font-bold tracking-wider text-text uppercase">{t('header.notifications')}</span>
          {data.length > 0 && (
            <Button variant="ghost" size="xs" onClick={() => markAll.mutate()} loading={markAll.isPending}>
              {t('header.markAllRead')}
            </Button>
          )}
        </div>
        {data.length === 0 ? (
          <p className="m-0 py-6 text-center text-sm text-text-3">{t('header.noNotifications')}</p>
        ) : (
          <ScrollArea className="max-h-[420px] [&>[data-slot=scroll-area-viewport]]:max-h-[420px]">
            <ul className="m-0 list-none p-0">
              {data.map((notification) => (
                <li key={notification.id}>
                  <button
                    type="button"
                    className="flex w-full cursor-pointer flex-col items-start gap-1 border-b border-border px-3 py-2 text-left transition-colors hover:bg-hover focus-visible:bg-hover focus-visible:outline-none"
                    onClick={() => open(notification)}
                  >
                    <span className="text-sm font-semibold text-text">{e('notification_kind', kindOf(notification))}</span>
                    {subjectOf(notification) && <Badge variant="outline">{subjectOf(notification)}</Badge>}
                    <span className="text-xs text-text-3 tabular-nums">{dateTime(notification.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </ScrollArea>
        )}
      </PopoverContent>
    </Popover>
  );
}
