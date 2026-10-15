import i18next, { type TOptions } from 'i18next';
import kk from '../../src/i18n/locales/kk';
import ru from '../../src/i18n/locales/ru';

type Translate = (key: string, options?: TOptions) => string;

/**
 * The app's own translations, resolved like the app does it (`namespace:key`, plurals, interpolation), so the
 * suite asserts the wording of the locale files instead of copies of it. A missing key is an error, not the key.
 */
function createTranslate(language: 'ru' | 'kk'): Translate {
  const instance = i18next.createInstance();
  void instance.init({
    resources: { ru, kk },
    lng: language,
    fallbackLng: false,
    ns: Object.keys(ru),
    defaultNS: 'common',
    interpolation: { escapeValue: false },
    initAsync: false,
    parseMissingKeyHandler: (key) => {
      throw new Error(`Missing i18n key: ${key}`);
    },
  });
  return (key, options) => String(instance.t(key, options));
}

export const t = createTranslate('ru');
export const tKk = createTranslate('kk');

const escapeRegExp = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** A regular expression of a translated string whose interpolated values are digits, e.g. «узлов 98, связей 125». */
export function numberedPattern(key: string, params: string[], options: TOptions = {}): RegExp {
  const marks = Object.fromEntries(params.map((name) => [name, `\u0000${name}\u0000`]));
  let source = escapeRegExp(t(key, { ...options, ...marks }));
  for (const name of params) source = source.replaceAll(`\u0000${name}\u0000`, '\\d+');
  return new RegExp(source);
}
