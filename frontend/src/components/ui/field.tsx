import { useMemo } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { Label } from '@/components/ui/label';
import { cn } from '@/lib/utils';

/** Wrappers that lay out a form control with its label, hint and error (see `components/form` for ready-made inputs). */
function FieldSet({ className, ...props }: React.ComponentProps<'fieldset'>) {
  return <fieldset data-slot="field-set" className={cn('flex flex-col gap-3', className)} {...props} />;
}

function FieldLegend({ className, ...props }: React.ComponentProps<'legend'>) {
  return <legend data-slot="field-legend" className={cn('mb-1.5 text-2xs font-bold tracking-wider text-text uppercase', className)} {...props} />;
}

function FieldGroup({ className, ...props }: React.ComponentProps<'div'>) {
  return <div data-slot="field-group" className={cn('group/field-group @container/field-group flex w-full flex-col gap-3', className)} {...props} />;
}

const fieldVariants = cva('group/field flex w-full gap-1', {
  variants: {
    orientation: {
      vertical: 'flex-col *:w-full [&>.sr-only]:w-auto',
      horizontal: 'flex-row items-center gap-2 has-[>[data-slot=field-content]]:items-start',
      responsive: 'flex-col *:w-full @md/field-group:flex-row @md/field-group:items-center @md/field-group:*:w-auto [&>.sr-only]:w-auto',
    },
  },
  defaultVariants: { orientation: 'vertical' },
});

function Field({ className, orientation = 'vertical', ...props }: React.ComponentProps<'div'> & VariantProps<typeof fieldVariants>) {
  return <div role="group" data-slot="field" data-orientation={orientation} className={cn(fieldVariants({ orientation }), className)} {...props} />;
}

function FieldContent({ className, ...props }: React.ComponentProps<'div'>) {
  return <div data-slot="field-content" className={cn('group/field-content flex flex-1 flex-col gap-0.5 leading-snug', className)} {...props} />;
}

function FieldLabel({ className, ...props }: React.ComponentProps<typeof Label>) {
  return <Label data-slot="field-label" className={cn('w-fit gap-1 group-data-[disabled=true]/field:opacity-50', className)} {...props} />;
}

function FieldTitle({ className, ...props }: React.ComponentProps<'div'>) {
  return <div data-slot="field-label" className={cn('flex w-fit items-center gap-2 text-xs font-medium text-text-2', className)} {...props} />;
}

function FieldDescription({ className, ...props }: React.ComponentProps<'p'>) {
  return <p data-slot="field-description" className={cn('text-xs leading-snug font-normal text-text-3 [&>a]:text-link [&>a]:underline [&>a]:underline-offset-2', className)} {...props} />;
}

function FieldSeparator({ children, className, ...props }: React.ComponentProps<'div'> & { children?: React.ReactNode }) {
  return (
    <div data-slot="field-separator" className={cn('relative -my-1 h-4 text-xs', className)} {...props}>
      <div className="absolute inset-x-0 top-1/2 h-px bg-border" />
      {children && <span className="relative mx-auto block w-fit bg-surface px-2 text-text-3">{children}</span>}
    </div>
  );
}

/** Pass the message as `children`, or react-hook-form's `errors` (one message, or a list for several). */
function FieldError({
  className,
  children,
  errors,
  ...props
}: React.ComponentProps<'div'> & { errors?: Array<{ message?: string } | undefined> }) {
  const content = useMemo(() => {
    if (children) return children;
    if (!errors?.length) return null;
    const unique = [...new Map(errors.map((error) => [error?.message, error])).values()];
    if (unique.length === 1) return unique[0]?.message;
    return (
      <ul className="ml-4 flex list-disc flex-col gap-0.5">
        {unique.map((error, index) => error?.message && <li key={index}>{error.message}</li>)}
      </ul>
    );
  }, [children, errors]);

  if (!content) return null;
  return (
    <div data-slot="field-error" className={cn('text-xs font-normal text-zone-red-ink', className)} {...props}>
      {content}
    </div>
  );
}

export { Field, FieldLabel, FieldDescription, FieldError, FieldGroup, FieldLegend, FieldSeparator, FieldSet, FieldContent, FieldTitle };
