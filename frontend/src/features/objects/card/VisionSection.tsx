import { useState } from 'react';
import { IconPlus } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { useVisionEnabled, useVisionSessions } from '@/api/hooks/vision';
import type { ObjectDetail } from '@/api/types';
import { Chip } from '@/components/Chip';
import { DemoBadge } from '@/components/DemoBadge';
import { Panel } from '@/components/Panel';
import { ErrorBlock, LoadingBlock } from '@/components/QueryState';
import { Button } from '@/components/ui/button';
import { NewSessionDialog } from '@/features/vision/NewSessionDialog';
import { SessionStatusChips } from '@/features/vision/SessionStatusChips';
import { useEnum } from '@/i18n/useEnum';
import { useFormat } from '@/i18n/useFormat';

const LIMIT = 10;

function VisionSectionBody({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('vision');
  const e = useEnum();
  const f = useFormat();
  const [creating, setCreating] = useState(false);
  const query = useVisionSessions({ object_id: object.id, limit: LIMIT });

  let body;
  if (query.isPending) body = <LoadingBlock />;
  else if (query.isError) body = <ErrorBlock error={query.error} onRetry={() => void query.refetch()} />;
  else if (query.data.items.length === 0) body = <p className="px-4 pb-4 text-text-3">{t('card.empty')}</p>;
  else {
    body = (
      <>
        <ul>
          {query.data.items.map((session) => (
            <li
              key={session.id}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border px-4 py-2.5 first:border-t-0"
              data-testid="vision-card-session"
            >
              <Link to={`/vision/${session.id}`} className="font-semibold tabular-nums">
                {f.dateTime(session.captured_at ?? session.created_at)}
              </Link>
              {session.is_demo && <DemoBadge />}
              <Chip>{e('vision_source', session.source)}</Chip>
              <SessionStatusChips session={session} />
              <span className="ml-auto text-text-2 tabular-nums">
                {t('card.counts', { files: session.assets_count, findings: session.findings_count })}
              </span>
            </li>
          ))}
        </ul>
        {query.data.total > LIMIT && (
          <p className="m-0 border-t border-border px-4 py-2 text-xs text-text-3">
            {t('card.more', { shown: LIMIT, total: query.data.total })}
          </p>
        )}
      </>
    );
  }

  return (
    <Panel
      title={t('card.title')}
      id="vision"
      flush
      actions={
        <Button variant="secondary" size="sm" onClick={() => setCreating(true)}>
          <IconPlus />
          {t('create')}
        </Button>
      }
    >
      {body}
      {creating && <NewSessionDialog opened onClose={() => setCreating(false)} defaultObjectId={object.id} />}
    </Panel>
  );
}

/** Visual inspections of the object. Shown only while the module is on; it does not touch the readiness or the risk. */
export function VisionSection({ object }: { object: ObjectDetail }) {
  const enabled = useVisionEnabled();
  if (!enabled) return null;
  return <VisionSectionBody object={object} />;
}
