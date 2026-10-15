import * as React from 'react';
import type { VariantProps } from 'class-variance-authority';
import { ToggleGroup as ToggleGroupPrimitive } from 'radix-ui';
import { toggleVariants } from '@/components/ui/toggle';
import { cn } from '@/lib/utils';

const ToggleGroupContext = React.createContext<VariantProps<typeof toggleVariants>>({ size: 'md' });

/**
 * Segmented control (replaces the Mantine SegmentedControl): joined buttons in a sunken frame.
 * `type="single"` lets a click on the active item clear the value, so guard `onValueChange` with `(v) => v && set(v)`.
 */
function ToggleGroup({ className, size = 'md', children, ...props }: React.ComponentProps<typeof ToggleGroupPrimitive.Root> & VariantProps<typeof toggleVariants>) {
  return (
    <ToggleGroupPrimitive.Root
      data-slot="toggle-group"
      data-size={size}
      className={cn(
        'inline-flex w-fit items-stretch gap-px rounded border border-border-strong bg-surface-sunken p-px data-[size=md]:h-7 data-[size=sm]:h-6',
        className,
      )}
      {...props}
    >
      <ToggleGroupContext.Provider value={{ size }}>{children}</ToggleGroupContext.Provider>
    </ToggleGroupPrimitive.Root>
  );
}

function ToggleGroupItem({ className, children, ...props }: React.ComponentProps<typeof ToggleGroupPrimitive.Item>) {
  const { size } = React.useContext(ToggleGroupContext);
  return (
    <ToggleGroupPrimitive.Item
      data-slot="toggle-group-item"
      className={cn(toggleVariants({ size }), 'h-full min-w-0 rounded-[2px] focus-visible:z-10', className)}
      {...props}
    >
      {children}
    </ToggleGroupPrimitive.Item>
  );
}

export { ToggleGroup, ToggleGroupItem };
