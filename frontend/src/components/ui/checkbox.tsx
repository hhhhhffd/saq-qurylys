import * as React from 'react';
import { IconCheck, IconMinus } from '@tabler/icons-react';
import { Checkbox as CheckboxPrimitive } from 'radix-ui';
import { cn } from '@/lib/utils';

/** 12px square on the sunken surface; pink fill when checked. */
function Checkbox({ className, ...props }: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        'peer relative flex size-3 shrink-0 items-center justify-center rounded-[2px] border border-border-strong bg-surface-sunken text-primary-foreground outline-none transition-colors after:absolute after:-inset-1.5 hover:border-text-disabled focus-visible:ring-1 focus-visible:ring-focus disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-zone-red aria-invalid:ring-1 aria-invalid:ring-zone-red data-[state=checked]:border-primary data-[state=checked]:bg-primary data-[state=indeterminate]:border-primary data-[state=indeterminate]:bg-primary',
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator data-slot="checkbox-indicator" className="grid place-content-center text-current [&>svg]:size-2.5">
        {props.checked === 'indeterminate' ? <IconMinus stroke={3.5} /> : <IconCheck stroke={3.5} />}
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}

export { Checkbox };
