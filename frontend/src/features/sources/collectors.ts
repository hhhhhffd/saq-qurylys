import type { CollectorStatus, Platform, SourceAccount } from '@/api/types';

/** What is switched on in `.env`: a collector per platform, and for the aggregator one per supported site. */
export type CollectorSource = 'instagram' | 'telegram' | 'olx' | 'krisha';

export const COLLECTOR_SOURCES: readonly CollectorSource[] = ['instagram', 'telegram', 'olx', 'krisha'];

/** Platforms a source can be added for by hand; the others (TikTok, sites) are only added by link. */
export const SOURCE_PLATFORMS: readonly Platform[] = ['telegram', 'instagram', 'aggregator'];

const SITE_HOSTS: Record<string, 'olx' | 'krisha'> = { 'olx.kz': 'olx', 'krisha.kz': 'krisha' };

/** `olx` or `krisha` for an address on one of the supported sites (`www.` is optional), else null. */
export function aggregatorSite(url: string | null | undefined): 'olx' | 'krisha' | null {
  if (!url) return null;
  try {
    const { protocol, hostname } = new URL(url);
    if (protocol !== 'http:' && protocol !== 'https:') return null;
    return SITE_HOSTS[hostname.toLowerCase().replace(/^www\./, '')] ?? null;
  } catch {
    return null;
  }
}

/** The collector an account depends on; null when its platform has no automatic collection. */
export function collectorOf(account: Pick<SourceAccount, 'platform' | 'url'>): CollectorSource | null {
  if (account.platform === 'instagram' || account.platform === 'telegram') return account.platform;
  return account.platform === 'aggregator' ? aggregatorSite(account.url) : null;
}

export function isCollectorOn(source: CollectorSource, collectors: CollectorStatus[]): boolean {
  if (source === 'olx' || source === 'krisha') {
    return collectors.find((item) => item.platform === 'aggregator')?.sources[source] ?? false;
  }
  return collectors.find((item) => item.platform === source)?.enabled ?? false;
}
