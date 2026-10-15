import { useState } from 'react';
import { ActionIcon, Button, Tooltip } from '@mantine/core';
import { IconPlus, IconTrash } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { useDeleteLinkedEntity } from '@/api/hooks/objects';
import type { LinkedEntity, LinkedEntityKind, ObjectDetail } from '@/api/types';
import { useAuth } from '@/auth/useAuth';
import { Panel } from '@/components/Panel';
import { useEnum } from '@/i18n/useEnum';
import { confirmAction } from '@/lib/confirm';
import { LinkedEntityFormModal } from '../forms/LinkedEntityFormModal';
import classes from './Section.module.css';

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
          <Button variant="default" size="xs" leftSection={<IconPlus size={14} />} onClick={() => setAdding(true)}>
            {t('card.linked.add')}
          </Button>
        )
      }
    >
      {groups.length === 0 ? (
        <p className={classes.muted}>{t('card.linked.empty')}</p>
      ) : (
        groups.map((group) => (
          <section key={group.kind} className={classes.group} aria-labelledby={`linked-${group.kind}`}>
            <h4 id={`linked-${group.kind}`} className={classes.subTitle}>
              {e('linked_kind', group.kind)}
            </h4>
            <ul className={classes.list}>
              {group.items.map((entity) => (
                <li key={entity.id} className={classes.entityRow}>
                  <div className={classes.entityValue}>
                    {entity.kind === 'website' && WEB_URL.test(entity.value) ? (
                      <a href={entity.value} target="_blank" rel="noreferrer noopener">
                        {entity.value}
                      </a>
                    ) : (
                      entity.value
                    )}
                    {entity.note && <span className={classes.sub}>{entity.note}</span>}
                  </div>
                  {canEditRegistry && (
                    <Tooltip label={t('delete', { ns: 'common' })}>
                      <ActionIcon
                        variant="subtle"
                        color="gray"
                        aria-label={`${t('delete', { ns: 'common' })}: ${entity.value}`}
                        onClick={() => confirmDelete(entity)}
                      >
                        <IconTrash size={16} />
                      </ActionIcon>
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
