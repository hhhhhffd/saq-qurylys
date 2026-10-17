import { useState } from 'react';
import { IconFileDescription } from '@tabler/icons-react';
import { useTranslation } from 'react-i18next';
import { downloadFile } from '@/api/client';
import { errorMessage } from '@/api/queryClient';
import { Button } from '@/components/ui/button';
import { toast } from '@/lib/toast';

/** Downloads the case file PDF of the object; generation takes seconds, so the button shows a busy state. */
export function DossierButton({ objectId, code }: { objectId: number; code: string }) {
  const { t } = useTranslation('objects');
  const [loading, setLoading] = useState(false);

  const download = async () => {
    setLoading(true);
    try {
      await downloadFile(`/objects/${objectId}/dossier.pdf`, `${code}-dossier.pdf`);
    } catch (error) {
      toast.error(errorMessage(error), { title: t('dossier.error') });
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button variant="secondary" loading={loading} onClick={() => void download()}>
      <IconFileDescription />
      {t('dossier.button')}
    </Button>
  );
}
