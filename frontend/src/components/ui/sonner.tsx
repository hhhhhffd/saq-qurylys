import { IconAlertTriangle, IconCircleCheck, IconInfoCircle, IconLoader2, IconAlertOctagon } from '@tabler/icons-react';
import { Toaster as Sonner, type ToasterProps } from 'sonner';

/**
 * Mount once (Providers.tsx does). Raised surface; a colored bar on the left tells the kind: pink for success,
 * red for errors. Use `toast` from `@/lib/toast`, not sonner directly.
 */
function Toaster(props: ToasterProps) {
  return (
    <Sonner
      theme="dark"
      position="top-right"
      visibleToasts={4}
      icons={{
        success: <IconCircleCheck className="size-4 text-accent-text" />,
        info: <IconInfoCircle className="size-4 text-text-2" />,
        warning: <IconAlertTriangle className="size-4 text-zone-yellow-ink" />,
        error: <IconAlertOctagon className="size-4 text-zone-red-ink" />,
        loading: <IconLoader2 className="size-4 animate-spin text-text-2" />,
      }}
      style={
        {
          '--normal-bg': 'var(--surface-raised)',
          '--normal-text': 'var(--text)',
          '--normal-border': 'var(--border-strong)',
          '--border-radius': 'var(--radius)',
          fontFamily: 'var(--font-sans)',
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          // Sonner's own CSS is unlayered, so utilities need `!` to win over it.
          toast: 'border-l-[3px]! text-sm! shadow-2! data-[type=error]:border-l-zone-red! data-[type=success]:border-l-primary!',
          title: 'font-semibold!',
          description: 'text-text-2!',
        },
      }}
      {...props}
    />
  );
}

export { Toaster };
