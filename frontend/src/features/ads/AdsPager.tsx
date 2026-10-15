import { ActionIcon } from '@mantine/core';
import { IconChevronLeft, IconChevronRight } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { PAGE_SIZE } from './constants';
import classes from './AdsPager.module.css';

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
    <nav className={classes.pager} aria-label={t('feed.pagination', { ns: 'ads' })}>
      <span className="tnum muted">{t('pagination.range', { from, to, total })}</span>
      <div className={classes.controls}>
        <ActionIcon
          variant="default"
          aria-label={t('pagination.prev')}
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          <IconChevronLeft size={16} stroke={1.8} />
        </ActionIcon>
        <span className="tnum muted">{t('pagination.page', { page, pages })}</span>
        <ActionIcon
          variant="default"
          aria-label={t('pagination.next')}
          disabled={page >= pages}
          onClick={() => onPageChange(page + 1)}
        >
          <IconChevronRight size={16} stroke={1.8} />
        </ActionIcon>
      </div>
    </nav>
  );
}
