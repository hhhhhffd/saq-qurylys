import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import kk from './locales/kk';
import ru from './locales/ru';
import type { Locale } from '@/api/types';

const LANG_KEY = 'saq_lang';

export const namespaces = ['common', 'enums', 'map', 'objects', 'objectForms', 'ads', 'signals', 'admin'] as const;

export function getStoredLanguage(): Locale | null {
  try {
    const value = localStorage.getItem(LANG_KEY);
    return value === 'ru' || value === 'kk' ? value : null;
  } catch {
    return null;
  }
}

/** Switches the UI language and remembers the choice on this device. */
export function setLanguage(language: Locale): void {
  try {
    localStorage.setItem(LANG_KEY, language);
  } catch {
    // Persistence is best-effort.
  }
  void i18n.changeLanguage(language);
}

void i18n.use(initReactI18next).init({
  resources: { ru, kk },
  lng: getStoredLanguage() ?? 'ru',
  fallbackLng: 'ru',
  ns: [...namespaces],
  defaultNS: 'common',
  interpolation: { escapeValue: false },
  initAsync: false,
});

i18n.on('languageChanged', (language) => {
  document.documentElement.lang = language;
});
document.documentElement.lang = i18n.language;

export default i18n;
