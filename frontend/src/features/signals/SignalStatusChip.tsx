import type { SignalStatus } from '@/api/types';
import { Chip, type ChipTone } from '@/components/Chip';
import { useEnum } from '@/i18n/useEnum';

// Statuses stay calm: only "needs the officer" is yellow, red is reserved for the overdue chip.
const APPEARANCE: Record<SignalStatus, { tone: ChipTone; outline?: boolean }> = {
  requires_confirmation: { tone: 'yellow' },
  returned: { tone: 'yellow', outline: true },
  sent: { tone: 'info' },
  responded: { tone: 'info', outline: true },
  closed: { tone: 'neutral' },
};

export function SignalStatusChip({ status }: { status: SignalStatus }) {
  const e = useEnum();
  const { tone, outline } = APPEARANCE[status];
  return (
    <Chip tone={tone} outline={outline}>
      {e('signal_status', status)}
    </Chip>
  );
}
