import { Skeleton } from '@mantine/core';
import { IconFileOff } from '@tabler/icons-react';
import { EvidenceThumbs } from '@/components/evidence/EvidenceImage';
import { useEvidenceMeta } from '@/api/hooks/misc';
import classes from './EvidenceList.module.css';

const SIZE = 56;

function EvidenceItem({ id }: { id: number }) {
  const { data, isPending, isError } = useEvidenceMeta(id);
  if (isPending) return <Skeleton width={SIZE} height={SIZE} radius="md" />;
  if (isError) return <IconFileOff size={18} stroke={1.5} className={classes.failed} />;
  return <EvidenceThumbs evidence={[data]} size={SIZE} />;
}

/** Evidence attached to a card section; the card stores ids only, so metadata is loaded per item. */
export function EvidenceList({ ids }: { ids: number[] }) {
  if (ids.length === 0) return <span className="faint">—</span>;
  return (
    <div className={classes.root}>
      {ids.map((id) => (
        <EvidenceItem key={id} id={id} />
      ))}
    </div>
  );
}
