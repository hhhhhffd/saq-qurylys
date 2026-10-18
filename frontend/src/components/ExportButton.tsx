import { useState } from 'react';
import { IconFileSpreadsheet } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { downloadFile } from '@/api/client';
import { errorMessage } from '@/api/queryClient';
import { Button } from '@/components/ui/button';
import { toast } from '@/lib/toast';

interface Props {
  /** export endpoint, e.g. `/objects/export.xlsx` */
  path: string;
  /** the filters of the list on screen; empty values are left out */
  params: Record<string, string | number | undefined>;
  filename: string;
}

/** Downloads the registry as Excel with the filters of the list; the export is not paged. */
export function ExportButton({ path, params, filename }: Props) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);

  const download = async () => {
    setLoading(true);
    try {
      const query = new URLSearchParams();
      for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== '') query.set(key, String(value));
      }
      const suffix = query.size > 0 ? `?${query}` : '';
      await downloadFile(`${path}${suffix}`, filename);
    } catch (error) {
      toast.error(errorMessage(error), { title: t('error') });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button className="min-h-11" variant="secondary" loading={loading} onClick={() => void download()}>
      <IconFileSpreadsheet />
      {t('exportExcel')}
    </Button>
  );
}
