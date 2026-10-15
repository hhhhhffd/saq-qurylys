import * as React from 'react';
import { controlClass } from '@/components/ui/styles';
import { cn } from '@/lib/utils';

function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        controlClass,
        'file:mr-2 file:inline-flex file:border-0 file:bg-transparent file:text-xs file:font-medium file:text-text',
        className,
      )}
      {...props}
    />
  );
}

export { Input };
