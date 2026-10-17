import type { SignalStatus } from '@/api/types';
import { Chip, type ChipTone } from '@/components/Chip';
import { useTranslation } from 'react-i18next';

// Statuses stay calm: only "needs the officer" is yellow, red is reserved for the overdue chip.
const APPEARANCE: Record<SignalStatus, { tone: ChipTone; outline?: boolean }> = {
  requires_confirmation: { tone: 'yellow' },
  returned: { tone: 'yellow', outline: true },
  sent: { tone: 'info' },
  responded: { tone: 'info', outline: true },
  closed: { tone: 'green' },
};

export function SignalStatusChip({ status }: { status: SignalStatus }) {
  const { t } = useTranslation('signals');
  const { tone, outline } = APPEARANCE[status];
  return (
    <Chip tone={tone} outline={outline}>
      {t(`statusLabels.${status}`)}
    </Chip>
  );
}
