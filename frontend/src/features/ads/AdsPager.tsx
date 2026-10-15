import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { PAGE_SIZE } from './constants';

interface Props {
  page: number;
  total: number;
  onPageChange: (page: number) => void;
}

export function AdsPager({ page, total, onPageChange }: Props) {
  const { t } = useTranslation();
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const from = (page - 1) * PAGE_SIZE + 1;
  const to = Math.min(page * PAGE_SIZE, total);

  return (
    <nav className="mt-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-sm text-text-3" aria-label={t('feed.pagination', { ns: 'ads' })}>
      <span className="tabular-nums">{t('pagination.range', { from, to, total })}</span>
      <div className="flex items-center gap-2.5">
        <Button
          variant="secondary"
          size="icon"
          aria-label={t('pagination.prev')}
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <IconChevronLeft />
        </Button>
        <span className="tabular-nums">{t('pagination.page', { page, pages })}</span>
        <Button
          variant="secondary"
          size="icon"
          aria-label={t('pagination.next')}
          disabled={page >= pages}
          onClick={() => onPageChange(page + 1)}
        >
          <IconChevronRight />
        </Button>
      </div>
    </nav>
  );
}
