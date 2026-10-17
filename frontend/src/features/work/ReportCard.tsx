import { useState } from 'react';
import { IconFileTypePdf } from '@tabler/icons-react';
import { startOfMonth } from 'date-fns';
import { useTranslation } from 'react-i18next';
import { downloadFile } from '@/api/client';
import { errorMessage } from '@/api/queryClient';
import { formatApiDate } from '@/components/form/dates';
import { DateInput } from '@/components/form/DateInput';
import { Button } from '@/components/ui/button';
import { toast } from '@/lib/toast';

/** "Report to the management": a PDF for a period over the user's own territory. */
export function ReportCard() {
  const { t } = useTranslation();
  const [from, setFrom] = useState<string | null>(() => formatApiDate(startOfMonth(new Date())));
  const [to, setTo] = useState<string | null>(() => formatApiDate(new Date()));
  const [loading, setLoading] = useState(false);
  const reversed = from !== null && to !== null && from > to;

  const download = async () => {
    if (!from || !to) return;
    setLoading(true);
    try {
      await downloadFile(`/dashboard/report.pdf?from=${from}&to=${to}`, `doklad-${from}-${to}.pdf`);
    } catch (error) {
      toast.error(errorMessage(error), { title: t('error') });
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="space-y-3 rounded border border-border bg-surface p-3" aria-labelledby="work-report-title">
      <div>
        <h2 id="work-report-title" className="text-lg font-semibold">
          {t('report.title')}
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-text-3">{t('report.note')}</p>
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <DateInput label={t('report.from')} value={from} onChange={setFrom} maxDate={to ?? undefined} className="w-44" />
        <DateInput label={t('report.to')} value={to} onChange={setTo} minDate={from ?? undefined} className="w-44" />
        <Button
          variant="secondary"
          loading={loading}
          disabled={!from || !to || reversed}
          className="min-h-11"
          onClick={() => void download()}
        >
          <IconFileTypePdf />
          {t('report.button')}
        </Button>
      </div>
      {reversed && <p className="m-0 text-xs text-zone-red-ink">{t('report.invalidRange')}</p>}
    </section>
  );
}
