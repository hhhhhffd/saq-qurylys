import {
  IconAlertTriangle,
  IconClockExclamation,
  IconCompass,
  IconFileSearch,
  IconLink,
  IconListCheck,
  IconListDetails,
  IconMessageReply,
  IconReceipt,
  IconSend,
  IconSortDescending,
  IconSparkles,
  IconTrafficCone,
  type Icon,
} from '@tabler/icons-react';
import type { PageContext } from './pageContext';

export type StarterKind = 'object' | 'ads' | 'work' | 'signals' | 'general';

/** Icons of the starter cards; the texts are `starters.<kind>.<index>.title|subtitle` in the `assistant` namespace. */
export const starterIcons: Record<StarterKind, Icon[]> = {
  object: [IconAlertTriangle, IconFileSearch, IconSend],
  ads: [IconSparkles, IconLink, IconReceipt],
  work: [IconListCheck, IconClockExclamation, IconSortDescending],
  signals: [IconSend, IconListDetails, IconMessageReply],
  general: [IconCompass, IconTrafficCone, IconSend, IconFileSearch],
};

export function starterKind({ entity, section }: PageContext): StarterKind {
  if (entity?.type === 'object') return 'object';
  if (entity?.type === 'signal' || section === 'signals') return 'signals';
  if (section === 'ads') return 'ads';
  if (section === 'work') return 'work';
  return 'general';
}
