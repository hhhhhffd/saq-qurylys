import type { ReactNode } from 'react';

interface Props {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

export function SectionHeader({ title, description, actions }: Props) {
  return (
    <div className="mb-3.5 flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
      <div className="min-w-0 max-w-[78ch]">
        <h2 className="font-heading text-sm font-bold tracking-wider uppercase">{title}</h2>
        {description && <p className="mt-1 text-xs text-text-2">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
