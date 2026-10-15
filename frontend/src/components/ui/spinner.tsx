import { IconLoader2 } from '@tabler/icons-react';
import { cn } from '@/lib/utils';

/** Rotating loader. Inherits the text color; size with `size-*`. */
function Spinner({ className, ...props }: React.ComponentProps<typeof IconLoader2>) {
  return (
    <IconLoader2
      role="status"
      aria-label="Loading"
      className={cn('size-4 animate-spin motion-reduce:animate-none', className)}
      {...props}
    />
  );
}

export { Spinner };
