import { useMemo } from 'react';
import { matchPath, useLocation } from 'react-router';

export type EntityType = 'object' | 'signal' | 'ad' | 'vision_session';

export interface PageContext {
  path: string;
  entity: { type: EntityType; id: number } | null;
  /** first path segment, for the label of a page without an entity */
  section: string;
}

const entityRoutes: Array<{ pattern: string; type: EntityType }> = [
  { pattern: '/objects/:id', type: 'object' },
  { pattern: '/signals/:id', type: 'signal' },
  { pattern: '/vision/:id', type: 'vision_session' },
];

/** What the assistant gets to know about the open page; the panel lives outside the routes, so it reads the URL itself. */
export function usePageContext(): PageContext {
  const { pathname, search } = useLocation();
  return useMemo(() => {
    let entity: PageContext['entity'] = null;
    for (const { pattern, type } of entityRoutes) {
      const id = Number(matchPath(pattern, pathname)?.params.id);
      if (Number.isInteger(id) && id > 0) entity = { type, id };
    }
    const adId = Number(new URLSearchParams(search).get('ad'));
    if (pathname === '/ads' && Number.isInteger(adId) && adId > 0) entity = { type: 'ad', id: adId };
    return { path: pathname, entity, section: pathname.split('/')[1] ?? '' };
  }, [pathname, search]);
}
