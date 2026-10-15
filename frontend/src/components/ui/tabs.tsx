import * as React from 'react';
import { Tabs as TabsPrimitive } from 'radix-ui';
import { cn } from '@/lib/utils';

function Tabs({ className, orientation = 'horizontal', ...props }: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return <TabsPrimitive.Root data-slot="tabs" data-orientation={orientation} className={cn('group/tabs flex gap-3 data-horizontal:flex-col', className)} {...props} />;
}

function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn('inline-flex w-fit items-end gap-4 border-b border-border group-data-vertical/tabs:flex-col group-data-vertical/tabs:items-stretch group-data-vertical/tabs:border-b-0 group-data-vertical/tabs:border-r', className)}
      {...props}
    />
  );
}

/** Caps label with an optional icon; inactive text-3, active pink with a pink underline (not color alone). */
function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "-mb-px inline-flex h-8 items-center justify-center gap-1.5 border-b-2 border-transparent px-0.5 text-xs font-semibold tracking-wider whitespace-nowrap text-text-3 uppercase outline-none transition-colors duration-(--dur) hover:text-text focus-visible:ring-1 focus-visible:ring-focus disabled:pointer-events-none disabled:text-text-disabled data-active:border-primary data-active:text-accent-text group-data-vertical/tabs:-mr-px group-data-vertical/tabs:mb-0 group-data-vertical/tabs:justify-start group-data-vertical/tabs:border-r-2 group-data-vertical/tabs:border-b-0 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className,
      )}
      {...props}
    />
  );
}

function TabsContent({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content data-slot="tabs-content" className={cn('flex-1 text-sm outline-none', className)} {...props} />;
}

export { Tabs, TabsList, TabsTrigger, TabsContent };
