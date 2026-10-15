import * as React from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

/**
 * An input frame with addons (icon, text or buttons) inside: `<InputGroup><InputGroupInput/><InputGroupAddon align="inline-end">…`.
 * The frame takes the focus ring and the red `aria-invalid` state of the control inside it.
 */
function InputGroup({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="input-group"
      role="group"
      className={cn(
        'group/input-group relative flex h-7 w-full min-w-0 items-center rounded border border-border-strong bg-surface-sunken text-sm text-text-2 transition-[color,border-color,box-shadow] duration-(--dur) outline-none has-[[data-slot=input-group-control]:focus-visible]:border-focus has-[[data-slot=input-group-control]:focus-visible]:ring-1 has-[[data-slot=input-group-control]:focus-visible]:ring-focus has-[[data-slot=input-group-control][aria-invalid=true]]:border-zone-red has-[[data-slot=input-group-control][aria-invalid=true]]:ring-1 has-[[data-slot=input-group-control][aria-invalid=true]]:ring-zone-red has-disabled:opacity-50 has-[>textarea]:h-auto',
        className,
      )}
      {...props}
    />
  );
}

function InputGroupAddon({ className, align = 'inline-start', ...props }: React.ComponentProps<'div'> & { align?: 'inline-start' | 'inline-end' }) {
  return (
    <div
      role="group"
      data-slot="input-group-addon"
      data-align={align}
      className={cn(
        'flex h-full cursor-text items-center justify-center gap-1.5 text-xs text-text-3 select-none data-[align=inline-end]:order-last data-[align=inline-end]:pr-1 data-[align=inline-start]:order-first data-[align=inline-start]:pl-2 [&>svg:not([class*="size-"])]:size-4',
        className,
      )}
      onClick={(event) => {
        if ((event.target as HTMLElement).closest('button')) return;
        event.currentTarget.parentElement?.querySelector<HTMLElement>('[data-slot=input-group-control]')?.focus();
      }}
      {...props}
    />
  );
}

function InputGroupButton({ className, type = 'button', variant = 'ghost', size = 'icon-xs', ...props }: React.ComponentProps<typeof Button>) {
  return <Button type={type} variant={variant} size={size} className={cn('shadow-none', className)} {...props} />;
}

function InputGroupText({ className, ...props }: React.ComponentProps<'span'>) {
  return <span className={cn('flex items-center gap-1.5 text-xs text-text-3 [&_svg]:pointer-events-none [&_svg:not([class*="size-"])]:size-4', className)} {...props} />;
}

const bareControl = 'h-full min-w-0 flex-1 border-0 bg-transparent px-2 text-sm text-text-2 outline-none placeholder:text-text-3 focus-visible:text-text disabled:cursor-not-allowed';

function InputGroupInput({ className, ...props }: React.ComponentProps<'input'>) {
  return <input data-slot="input-group-control" className={cn(bareControl, className)} {...props} />;
}

function InputGroupTextarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return <textarea data-slot="input-group-control" className={cn(bareControl, 'field-sizing-content min-h-16 resize-none py-1.5', className)} {...props} />;
}

export { InputGroup, InputGroupAddon, InputGroupButton, InputGroupText, InputGroupInput, InputGroupTextarea };
