import * as React from 'react';
import { Switch as SwitchPrimitive } from 'radix-ui';
import { cn } from '@/lib/utils';

/** Compact 28x14 switch; pink when on. */
function Switch({ className, ...props }: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        'peer relative inline-flex h-3.5 w-7 shrink-0 items-center rounded-[3px] border border-border-strong bg-surface-sunken p-px outline-none transition-colors after:absolute after:-inset-x-1 after:-inset-y-1.5 hover:border-text-disabled focus-visible:ring-1 focus-visible:ring-focus disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-zone-red data-[state=checked]:border-primary data-[state=checked]:bg-primary',
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className="pointer-events-none block size-2.5 rounded-[2px] bg-text-3 transition-transform duration-(--dur) ease-(--ease) data-[state=checked]:translate-x-3.5 data-[state=checked]:bg-primary-foreground"
      />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
