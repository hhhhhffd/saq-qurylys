import type { ChipTone } from '@/components/Chip';
import type { AdReviewState } from '@/api/types';

export const REVIEW_TONE: Record<AdReviewState, ChipTone> = {
  unreviewed: 'neutral',
  reviewed: 'green',
  deferred: 'yellow',
  irrelevant: 'neutral',
};
