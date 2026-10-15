import { Button } from '@mantine/core';
import { useTranslation } from 'react-i18next';
import type { GraphFinding, GraphNode } from '@/api/types';
import { Panel } from '@/components/Panel';
import { findingNodeId, formatPhone } from './graphModel';
import classes from './FindingsPanel.module.css';

interface Props {
  findings: GraphFinding[];
  nodes: GraphNode[];
  /** index of the finding that is shown on the graph */
  active: number | null;
  onSelect: (index: number | null) => void;
}

export function FindingsPanel({ findings, nodes, active, onSelect }: Props) {
  const { t } = useTranslation('graph');
  const labels = new Map(nodes.map((node) => [node.id, node.label]));

  return (
    <Panel
      title={t('findings.title')}
      actions={
        active !== null && (
          <Button variant="subtle" size="compact-xs" onClick={() => onSelect(null)}>
            {t('findings.clear')}
          </Button>
        )
      }
    >
      <p className={classes.hint}>{t('findings.hint')}</p>
      {findings.length === 0 ? (
        <p className={classes.empty}>{t('findings.empty')}</p>
      ) : (
        <ul className={classes.list}>
          {findings.map((finding, index) => {
            const label = labels.get(findingNodeId(finding)) ?? finding.value;
            return (
              <li key={findingNodeId(finding)}>
                <button
                  type="button"
                  className={classes.finding}
                  aria-pressed={active === index}
                  onClick={() => onSelect(active === index ? null : index)}
                >
                  <span className={classes.title}>
                    {t(`findings.${finding.kind}`, { count: finding.developer_ids.length, defaultValue: finding.label })}
                  </span>
                  <span className={`${classes.value} tnum`}>
                    {finding.kind === 'shared_phone' ? formatPhone(finding.value) : label}
                  </span>
                  <span className={classes.meta}>{t('findings.objects', { count: finding.object_ids.length })}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}
