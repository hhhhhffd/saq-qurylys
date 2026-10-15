import { useTranslation } from 'react-i18next';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { setLanguage } from '@/i18n';
import type { Locale } from '@/api/types';

export function LanguageSwitch({ className }: { className?: string }) {
  const { t, i18n } = useTranslation();
  return (
    <ToggleGroup
      type="single"
      size="sm"
      className={className}
      aria-label={t('header.language')}
      value={i18n.language === 'kk' ? 'kk' : 'ru'}
      onValueChange={(value) => value && setLanguage(value as Locale)}
    >
      <ToggleGroupItem value="ru" className="font-heading text-2xs font-semibold tracking-wider">
        RU
      </ToggleGroupItem>
      <ToggleGroupItem value="kk" className="font-heading text-2xs font-semibold tracking-wider">
        ҚАЗ
      </ToggleGroupItem>
    </ToggleGroup>
  );
}
