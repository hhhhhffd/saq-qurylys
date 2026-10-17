import type { ChipTone } from '@/components/Chip';
import type {
  FindingCategory,
  FindingReviewState,
  FindingStatus,
  VisionAssetStatus,
  VisionSessionStatus,
  VisionSource,
} from '@/api/types';

export const SOURCES: readonly VisionSource[] = ['drone', 'camera', 'phone', 'other'];
export const SESSION_STATUSES: readonly VisionSessionStatus[] = ['open', 'reviewed'];
export const CATEGORIES: readonly FindingCategory[] = [
  'outdoor_ad',
  'fence',
  'site_gate',
  'waste_container',
  'wheel_wash',
  'other',
];
export const SITE_CATEGORIES = CATEGORIES.filter((category) => category !== 'outdoor_ad');
export const FINDING_STATUSES: readonly FindingStatus[] = [
  'observed',
  'possible_noncompliance',
  'insufficient_evidence',
  'not_applicable',
];

export const isSource = (value: string | null): value is VisionSource => SOURCES.some((item) => item === value);
export const isSessionStatus = (value: string | null): value is VisionSessionStatus =>
  SESSION_STATUSES.some((item) => item === value);
export const isCategory = (value: string | null): value is FindingCategory => CATEGORIES.some((item) => item === value);
export const isFindingStatus = (value: string | null): value is FindingStatus =>
  FINDING_STATUSES.some((item) => item === value);

export const REVIEW_STATE_TONE: Record<FindingReviewState, ChipTone> = {
  pending: 'neutral',
  confirmed: 'green',
  rejected: 'neutral',
  needs_more_evidence: 'yellow',
};

export const FINDING_STATUS_TONE: Record<FindingStatus, ChipTone> = {
  observed: 'neutral',
  possible_noncompliance: 'yellow',
  insufficient_evidence: 'neutral',
  not_applicable: 'neutral',
};

export const ASSET_STATUS_TONE: Record<VisionAssetStatus, ChipTone> = {
  queued: 'neutral',
  processing: 'info',
  ready: 'green',
  failed: 'red',
};

const IMAGE_EXTENSIONS = ['jpg', 'jpeg', 'png', 'webp'];
const VIDEO_EXTENSIONS = ['mp4', 'mov', 'webm', 'mkv'];

/** The `accept` of the file picker: images (jpeg, png, webp) and videos (mp4, mov, webm, mkv). */
export const ACCEPT = [...IMAGE_EXTENSIONS, ...VIDEO_EXTENSIONS].map((ext) => `.${ext}`).join(',');

/** Kind of a picked file by its extension (browsers leave the MIME type of .mkv empty); null when it is not accepted. */
export function fileKind(file: File): 'photo' | 'video' | null {
  const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
  if (IMAGE_EXTENSIONS.includes(extension)) return 'photo';
  if (VIDEO_EXTENSIONS.includes(extension)) return 'video';
  return null;
}

/** `mm:ss` (`h:mm:ss` from an hour) of a position in a video. */
export function formatTimestamp(ms: number): string {
  const total = Math.floor(ms / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = String(total % 60).padStart(2, '0');
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, '0')}:${seconds}` : `${String(minutes).padStart(2, '0')}:${seconds}`;
}

export function formatSize(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}
