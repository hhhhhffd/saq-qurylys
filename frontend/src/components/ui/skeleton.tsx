import { cn } from '@/lib/utils';

/** Placeholder block; size it with `h-* w-*`. Static under prefers-reduced-motion. */
function Skeleton({ className, ...props }: React.ComponentProps<'div'>) {
  return <div data-slot="skeleton" className={cn('animate-pulse rounded bg-hover motion-reduce:animate-none', className)} {...props} />;
}

export { Skeleton };
