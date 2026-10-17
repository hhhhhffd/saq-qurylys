import { useTranslation } from 'react-i18next';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { setLanguage } from '@/i18n';
import type { Locale } from '@/api/types';

export function LanguageSwitch({ grouped = false }: { grouped?: boolean }) {
  const { t, i18n } = useTranslation();
  return (
    <ToggleGroup
      type="single"
      size="sm"
      className={grouped ? 'h-11 data-[size=sm]:h-11 border-0 bg-transparent p-0' : 'h-12 data-[size=sm]:h-12'}
      aria-label={t('header.language')}
      value={i18n.language === 'kk' ? 'kk' : 'ru'}
      onValueChange={(value) => value && setLanguage(value as Locale)}
    >
      <ToggleGroupItem value="ru" className="min-h-11 min-w-11 font-heading text-2xs font-semibold tracking-wider">
        RU
      </ToggleGroupItem>
      <ToggleGroupItem value="kk" className="min-h-11 min-w-11 font-heading text-2xs font-semibold tracking-wider">
        ҚАЗ
      </ToggleGroupItem>
    </ToggleGroup>
  );
}
