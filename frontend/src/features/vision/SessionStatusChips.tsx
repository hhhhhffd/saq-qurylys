import { useTranslation } from 'react-i18next';
import type { VisionSessionListItem } from '@/api/types';
import { Chip } from '@/components/Chip';
import { useEnum } from '@/i18n/useEnum';

/** What the session is doing: processing, failed files, or the review status. */
export function SessionStatusChips({ session }: { session: VisionSessionListItem }) {
  const { t } = useTranslation('vision');
  const e = useEnum();
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <Chip tone={session.status === 'reviewed' ? 'green' : 'neutral'}>{e('vision_session_status', session.status)}</Chip>
      {session.processing && <Chip tone="info">{t('processing')}</Chip>}
      {session.failed && <Chip tone="red">{t('failed')}</Chip>}
    </span>
  );
}
