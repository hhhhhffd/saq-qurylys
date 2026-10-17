import { useEffect, useRef, useState } from 'react';
import { IconCheck, IconCopy } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { toast } from '@/lib/toast';

const COPIED_MS = 1800;

/** Always-visible icon button that copies `value`; `label` is the tooltip and the accessible name («Копировать БИН»). */
export function CopyButton({ value, label }: { value: string; label: string }) {
  const { t } = useTranslation('objects');
  const { t: tc } = useTranslation('common');
  const [copied, setCopied] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const copy = () => {
    navigator.clipboard.writeText(value).then(
      () => {
        setCopied(true);
        window.clearTimeout(timer.current);
        timer.current = window.setTimeout(() => setCopied(false), COPIED_MS);
        // The icon swap is easy to miss, so the result is also announced with a toast.
        toast.success(t('copy.done'));
      },
      () => toast.error(tc('error')),
    );
  };

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button size="icon-xs" variant="ghost" aria-label={label} onClick={copy}>
          {copied ? <IconCheck /> : <IconCopy />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
