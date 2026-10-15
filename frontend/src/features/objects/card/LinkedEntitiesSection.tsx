import { useState } from 'react';
import { IconPlus, IconTrash } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useDeleteLinkedEntity } from '@/api/hooks/objects';
import type { LinkedEntity, LinkedEntityKind, ObjectDetail } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Panel } from '@/components/Panel';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useEnum } from '@/i18n/useEnum';
import { confirmAction } from '@/lib/confirm';
import { LinkedEntityFormModal } from '../forms/LinkedEntityFormModal';
import { subTitleClass } from './styles';

const KINDS: LinkedEntityKind[] = ['ad_account', 'sales_office', 'phone', 'website', 'bank_details'];
const WEB_URL = /^https?:\/\//i;

export function LinkedEntitiesSection({ object }: { object: ObjectDetail }) {
  const { t } = useTranslation('objects');
  const e = useEnum();
  const { canEditRegistry } = useAuth();
  const remove = useDeleteLinkedEntity();
  const [adding, setAdding] = useState(false);

  const groups = KINDS.map((kind) => ({
    kind,
    items: object.linked_entities.filter((entity) => entity.kind === kind),
  })).filter((group) => group.items.length > 0);

  const confirmDelete = (entity: LinkedEntity) =>
    confirmAction({
      title: t('card.linked.deleteTitle'),
      message: t('card.linked.deleteMessage', { value: entity.value }),
      confirmLabel: t('delete', { ns: 'common' }),
      danger: true,
      onConfirm: () => remove.mutate(entity.id),
    });

  return (
    <Panel
      title={t('card.linked.title')}
      id="linked-entities"
      actions={
        canEditRegistry && (
          <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
            <IconPlus />
            {t('card.linked.add')}
          </Button>
        )
      }
    >
      {groups.length === 0 ? (
        <p className="text-text-3">{t('card.linked.empty')}</p>
      ) : (
        groups.map((group) => (
          <section key={group.kind} className="not-first:mt-4" aria-labelledby={`linked-${group.kind}`}>
            <h4 id={`linked-${group.kind}`} className={`${subTitleClass} mb-1`}>
              {e('linked_kind', group.kind)}
            </h4>
            <ul>
              {group.items.map((entity) => (
                <li
                  key={entity.id}
                  className="flex min-h-7 items-start justify-between gap-2 border-t border-border py-1 first:border-t-0"
                >
                  <div className="min-w-0 py-0.5 [overflow-wrap:anywhere]">
                    {entity.kind === 'website' && WEB_URL.test(entity.value) ? (
                      <a href={entity.value} target="_blank" rel="noreferrer noopener">
                        {entity.value}
                      </a>
                    ) : (
                      entity.value
                    )}
                    {entity.note && <span className="block text-xs text-text-3">{entity.note}</span>}
                  </div>
                  {canEditRegistry && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          aria-label={`${t('delete', { ns: 'common' })}: ${entity.value}`}
                          onClick={() => confirmDelete(entity)}
                        >
                          <IconTrash />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>{t('delete', { ns: 'common' })}</TooltipContent>
                    </Tooltip>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))
      )}

      {canEditRegistry && (
        <LinkedEntityFormModal opened={adding} onClose={() => setAdding(false)} objectId={object.id} />
      )}
    </Panel>
  );
}
