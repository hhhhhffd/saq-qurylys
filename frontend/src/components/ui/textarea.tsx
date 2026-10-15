import * as React from 'react';
import { controlClass } from '@/components/ui/styles';
import { cn } from '@/lib/utils';

/** Grows with its content (`field-sizing-content`); cap it with `max-h-*`. */
function Textarea({ className, ...props }: React.ComponentProps<'textarea'>) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(controlClass, 'field-sizing-content h-auto min-h-16 py-1.5 leading-snug', className)}
      {...props}
    />
  );
}

export { Textarea };
