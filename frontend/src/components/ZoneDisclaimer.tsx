import { IconInfoCircle } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';

/** D16: must be visible wherever a zone is shown (dashboard, object card, signal card). */
export function ZoneDisclaimer({ className }: { className?: string }) {
  const { t } = useTranslation();
  return (
    <p className={cn('m-0 flex items-start gap-2 text-xs leading-snug text-text-2', className)} role="note">
      <IconInfoCircle size={15} stroke={1.8} className="mt-px flex-none" aria-hidden />
      <span>{t('disclaimer.zone')}</span>
    </p>
  );
}
