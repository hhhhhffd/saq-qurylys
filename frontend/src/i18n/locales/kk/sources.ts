// NOTE: Kazakh (kk) translations need native-speaker review.
import type ru from '../ru/sources';

const sources: typeof ru = {
  title: 'Дереккөздер',
  subtitle: 'Жүйе жарияланымдарды өзі жинайтын аккаунттар мен іздеулер. Жиналғандар «Жарнама» лентасына түседі.',
  backToAds: 'Жарнамаға',
  add: 'Дереккөз қосу',
  collectors: {
    title: 'Жинағыштар',
    on: 'қосулы',
    off: 'өшірулі — .env файлында қосылады',
    names: { instagram: 'Instagram', telegram: 'Telegram', olx: 'OLX.kz', krisha: 'Krisha.kz' },
  },
  columns: {
    platform: 'Платформа',
    source: 'Аккаунт немесе іздеу',
    object: 'Объект',
    territory: 'Аумақ',
    watched: 'Бақылау',
    lastCollected: 'Соңғы жинау',
    lastError: 'Қате',
  },
  empty: 'Дереккөздер әзірге жоқ. Арна, аккаунт немесе сақталған іздеуді қосыңыз.',
  notCollected: 'әлі жиналмаған',
  watch: '{{name}} дереккөзін бақылау',
  collectNow: 'Қазір жинау',
  collectOff: 'Бұл дереккөздің жинағышы өшірулі. Ол сервердің .env файлында қосылады.',
  collectUnsupported: 'Бұл платформа үшін автоматты жинау жоқ.',
  form: {
    title: 'Жаңа дереккөз',
    platform: 'Платформа',
    telegramHandle: 'Арна',
    telegramHandleHint: 'Ашық арна: @ белгісіз аты немесе t.me/… сілтемесі. t.me/s/<аты> беті ашылуы керек.',
    telegramHandlePlaceholder: 'zhk_alatau',
    instagramHandle: 'Аккаунт',
    instagramHandleHint: 'Тек бизнес-аккаунттар мен авторлар аккаунттары: жинау Instagram ресми API арқылы жүреді.',
    instagramHandlePlaceholder: 'zhk_alatau',
    label: 'Іздеу атауы',
    labelHint: 'Міндетті емес. Атауы болмаса, іздеу мекенжайы бойынша аталады.',
    labelPlaceholder: 'Өскемен жаңа құрылыстары, OLX',
    url: 'Іздеу сілтемесі',
    urlHint:
      'olx.kz немесе krisha.kz сайтындағы сақталған іздеу. OLX үшін API мекенжайын да көрсетуге болады: https://www.olx.kz/api/v1/offers/?query=…&city_id=…',
    urlPlaceholder: 'https://krisha.kz/prodazha/kvartiry/…',
    urlInvalid: 'olx.kz немесе krisha.kz сайтындағы іздеу сілтемесін көрсетіңіз',
    object: 'Объект (міндетті емес)',
    objectNote:
      'Объектіге байланған аккаунттың жарияланымдары баллға бірден есептеледі — тек тексерілген аккаунттарды байлаңыз.',
  },
};

export default sources;
