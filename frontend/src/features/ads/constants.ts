import type { AdReviewState, AdStatus, PaymentScheme, Platform } from '@/api/types';

export const PAGE_SIZE = 20;

export const PLATFORMS: readonly Platform[] = [
  'instagram',
  'tiktok',
  'telegram',
  'website',
  'aggregator',
  'outdoor',
  'other',
];
/** A URL capture never produces outdoor advertising. */
export const CAPTURE_PLATFORMS: readonly Platform[] = PLATFORMS.filter((platform) => platform !== 'outdoor');
export const AD_STATUSES: readonly AdStatus[] = ['captured', 'verification', 'removed_saved'];
export const AD_REVIEW_STATES: readonly AdReviewState[] = ['unreviewed', 'reviewed', 'deferred', 'irrelevant'];
export const PAYMENT_SCHEMES: readonly PaymentScheme[] = [
  'booking',
  'down_payment',
  'deposit',
  'installment',
  'nonstandard_contract',
];

/** SPEC §3 default of the `link_confidence_threshold` setting. */
export const DEFAULT_LINK_THRESHOLD = 0.8;

export function parsePlatform(value: string | null | undefined): Platform | null {
  return PLATFORMS.find((platform) => platform === value) ?? null;
}

export function parseAdStatus(value: string | null | undefined): AdStatus | null {
  return AD_STATUSES.find((status) => status === value) ?? null;
}

export function parseReviewState(value: string | null | undefined): AdReviewState | null {
  return AD_REVIEW_STATES.find((state) => state === value) ?? null;
}

export function parsePaymentSchemes(values: readonly string[]): PaymentScheme[] {
  return PAYMENT_SCHEMES.filter((scheme) => values.includes(scheme));
}

/** Ad and object ids come from the URL: only positive integers are accepted. */
export function parseId(value: string | null | undefined): number | null {
  const id = Number(value);
  return Number.isInteger(id) && id > 0 ? id : null;
}
