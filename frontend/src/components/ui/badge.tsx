import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Slot } from 'radix-ui';
import { cn } from '@/lib/utils';

/**
 * Chip: 10px caps on a tinted background. `green | yellow | red | none` are the zone tones (zones only!),
 * `default` is the pink brand tone, `secondary` the neutral one.
 */
const badgeVariants = cva(
  'inline-flex h-[18px] w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-sm border border-transparent px-1.5 text-3xs font-semibold tracking-wider whitespace-nowrap uppercase [&>svg]:pointer-events-none [&>svg]:size-3',
  {
    variants: {
      variant: {
        default: 'bg-primary/16 text-accent-text',
        secondary: 'bg-zone-none-bg text-zone-none-ink',
        outline: 'border-border-strong text-text-2',
        destructive: 'bg-zone-red-bg text-zone-red-ink',
        green: 'bg-zone-green-bg text-zone-green-ink',
        yellow: 'bg-zone-yellow-bg text-zone-yellow-ink',
        red: 'bg-zone-red-bg text-zone-red-ink',
        none: 'bg-zone-none-bg text-zone-none-ink',
      },
    },
    defaultVariants: { variant: 'secondary' },
  },
);

function Badge({
  className,
  variant,
  asChild = false,
  ...props
}: React.ComponentProps<'span'> & VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : 'span';
  return <Comp data-slot="badge" data-variant={variant ?? 'secondary'} className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
