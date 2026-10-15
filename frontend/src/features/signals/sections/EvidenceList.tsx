import { IconFileOff } from '@tabler/icons-react';
import { EvidenceThumbs } from '@/components/evidence/EvidenceImage';
import { Skeleton } from '@/components/ui/skeleton';
import { useEvidenceMeta } from '@/api/hooks/misc';

const SIZE = 56;

function EvidenceItem({ id }: { id: number }) {
  const { data, isPending, isError } = useEvidenceMeta(id);
  if (isPending) return <Skeleton className="size-14 rounded" />;
  if (isError) return <IconFileOff size={18} stroke={1.5} className="text-text-3" />;
  return <EvidenceThumbs evidence={[data]} size={SIZE} />;
}

/** Evidence attached to a card section; the card stores ids only, so metadata is loaded per item. */
export function EvidenceList({ ids }: { ids: number[] }) {
  if (ids.length === 0) return <span className="text-text-3">—</span>;
  return (
    <div className="flex flex-wrap items-center gap-2">
      {ids.map((id) => (
        <EvidenceItem key={id} id={id} />
      ))}
    </div>
  );
}
