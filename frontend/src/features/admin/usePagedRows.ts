import { useState } from 'react';

/** Client-side paging for the small admin tables (DataTable expects the current page only). */
export function usePagedRows<T>(rows: T[], pageSize: number) {
  const [requestedIndex, setPageIndex] = useState(0);
  const lastIndex = Math.max(0, Math.ceil(rows.length / pageSize) - 1);
  const pageIndex = Math.min(requestedIndex, lastIndex);
  return {
    pageIndex,
    setPageIndex,
    pageRows: rows.slice(pageIndex * pageSize, (pageIndex + 1) * pageSize),
  };
}
