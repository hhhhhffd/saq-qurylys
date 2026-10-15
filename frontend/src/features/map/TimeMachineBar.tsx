import { ActionIcon, Button, Loader, SegmentedControl, Slider } from '@mantine/core';
import { IconPlayerPauseFilled, IconPlayerPlayFilled, IconX } from '@tabler/icons-react';
import type { UseQueryResult } from '@tanstack/react-query';
import dayjs from 'dayjs';
import timezone from 'dayjs/plugin/timezone';
import utc from 'dayjs/plugin/utc';
import { useTranslation } from 'react-i18next';
import type { Timeline } from '@/api/types';
import { useTimeZone } from '@/i18n/useFormat';
import { SPEEDS, type Speed, type useTimeMachine } from './timeMachine';
import classes from './TimeMachineBar.module.css';

dayjs.extend(utc);
dayjs.extend(timezone);

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
    <ActionIcon size="lg" aria-label={t('timeMachine.close')} onClick={onClose}>
      <IconX size={18} stroke={1.8} />
    </ActionIcon>
  );

  if (timeline.isPending || timeline.isError || !frame) {
    return (
      <div className={classes.bar} role="group" aria-label={t('timeMachine.bar')}>
        <div className={classes.row}>
          {timeline.isPending && (
            <span className={classes.status} role="status">
              <Loader size="xs" />
              {t('timeMachine.loading')}
            </span>
          )}
          {timeline.isError && (
            <span className={classes.status} role="alert">
              {t('timeMachine.failed')}
              <Button variant="default" size="compact-xs" onClick={() => void timeline.refetch()}>
                {common('retry')}
              </Button>
            </span>
          )}
          {timeline.isSuccess && <span className={classes.status}>{t('timeMachine.empty')}</span>}
          {close}
        </div>
      </div>
    );
  }

  return (
    <div className={classes.bar} role="group" aria-label={t('timeMachine.bar')}>
      <div className={classes.row}>
        <ActionIcon
          size="lg"
          variant="default"
          aria-label={machine.playing ? t('timeMachine.pause') : t('timeMachine.play')}
          onClick={machine.togglePlay}
        >
          {machine.playing ? <IconPlayerPauseFilled size={16} /> : <IconPlayerPlayFilled size={16} />}
        </ActionIcon>
        <time className={`${classes.date} tnum`} dateTime={frame.at} data-testid="time-machine-date">
          {dateLabel(frame.at)}
          {machine.isToday && <span className={classes.today}> · {t('timeMachine.today')}</span>}
        </time>
        {close}
      </div>
      <div className={classes.row}>
        <Slider
          className={classes.slider}
          size="sm"
          min={0}
          max={machine.last}
          step={1}
          value={machine.index}
          onChange={machine.seek}
          label={null}
          thumbLabel={t('timeMachine.slider')}
        />
        <SegmentedControl
          size="xs"
          aria-label={t('timeMachine.speed')}
          data={SPEEDS.map((speed) => ({ value: String(speed), label: `×${speed}` }))}
          value={String(machine.speed)}
          disabled={machine.speedLocked}
          onChange={(value) => machine.setSpeed(Number(value) as Speed)}
        />
      </div>
    </div>
  );
}
