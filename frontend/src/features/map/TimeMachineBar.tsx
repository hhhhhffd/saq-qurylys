import { IconPlayerPauseFilled, IconPlayerPlayFilled, IconX } from '@tabler/icons-react';
import type { UseQueryResult } from '@tanstack/react-query';
import dayjs from 'dayjs';
import timezone from 'dayjs/plugin/timezone';
import utc from 'dayjs/plugin/utc';
import { useTranslation } from 'react-i18next';
import type { Timeline } from '@/api/types';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { Spinner } from '@/components/ui/spinner';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { useTimeZone } from '@/i18n/useFormat';
import { SPEEDS, type Speed, type useTimeMachine } from './timeMachine';

dayjs.extend(utc);
dayjs.extend(timezone);

/** Lies over the bottom of the map frame, above the attribution control. */
const BAR =
  'absolute inset-x-2 bottom-8 z-[3] mx-auto flex max-w-140 flex-col gap-1.5 rounded border border-border-strong bg-surface-glass px-2.5 pt-2 pb-2.5 shadow-2 backdrop-blur-md';
const ROW = 'flex min-w-0 items-center gap-2';
const STATUS = 'flex min-w-0 flex-1 items-center gap-2 text-sm text-text-2';

interface Props {
  timeline: UseQueryResult<Timeline>;
  machine: ReturnType<typeof useTimeMachine>;
  onClose: () => void;
}

/** Playback bar at the bottom of the map: play/pause, the date, speed and a slider over the frames. */
export function TimeMachineBar({ timeline, machine, onClose }: Props) {
  const { t, i18n } = useTranslation('map');
  const { t: common } = useTranslation();
  const timeZone = useTimeZone();
  const frames = timeline.data?.frames ?? [];
  const frame = frames[machine.index];
  const dateLabel = (at: string) => dayjs(at).tz(timeZone).locale(i18n.language).format('D MMMM YYYY');

  const close = (
    <Button size="icon" variant="ghost" aria-label={t('timeMachine.close')} onClick={onClose}>
      <IconX />
    </Button>
  );

  if (timeline.isPending || timeline.isError || !frame) {
    return (
      <div className={BAR} role="group" aria-label={t('timeMachine.bar')}>
        <div className={ROW}>
          {timeline.isPending && (
            <span className={STATUS} role="status">
              <Spinner className="size-3.5" />
              {t('timeMachine.loading')}
            </span>
          )}
          {timeline.isError && (
            <span className={STATUS} role="alert">
              {t('timeMachine.failed')}
              <Button variant="secondary" size="xs" onClick={() => void timeline.refetch()}>
                {common('retry')}
              </Button>
            </span>
          )}
          {timeline.isSuccess && <span className={STATUS}>{t('timeMachine.empty')}</span>}
          {close}
        </div>
      </div>
    );
  }

  return (
    <div className={BAR} role="group" aria-label={t('timeMachine.bar')}>
      <div className={ROW}>
        <Button
          size="icon"
          variant="secondary"
          aria-label={machine.playing ? t('timeMachine.pause') : t('timeMachine.play')}
          onClick={machine.togglePlay}
        >
          {machine.playing ? <IconPlayerPauseFilled /> : <IconPlayerPlayFilled />}
        </Button>
        <time
          className="min-w-0 flex-1 truncate font-heading text-base font-semibold tabular-nums" 
          dateTime={frame.at}
          data-testid="time-machine-date">
          {dateLabel(frame.at)}
          {machine.isToday && <span className="font-normal text-text-2"> · {t('timeMachine.today')}</span>}
        </time>
        {close}
      </div>
      <div className={ROW}>
        <Slider
          className="min-w-0 flex-1 px-1.5"
          min={0}
          max={machine.last}
          step={1}
          value={[machine.index]}
          onValueChange={([index]) => machine.seek(index)}
          thumbLabel={t('timeMachine.slider')}
        />
        <ToggleGroup
          type="single"
          size="sm"
          aria-label={t('timeMachine.speed')}
          value={String(machine.speed)}
          disabled={machine.speedLocked}
          onValueChange={(value) => value && machine.setSpeed(Number(value) as Speed)}
        >
          {SPEEDS.map((speed) => (
            <ToggleGroupItem key={speed} value={String(speed)} className="tabular-nums">
              ×{speed}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>
    </div>
  );
}
