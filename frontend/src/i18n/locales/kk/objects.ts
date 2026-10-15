// NOTE: Kazakh (kk) translations need native-speaker review.
import type ru from '../ru/objects';

const objects: typeof ru = {
  card: {
    back: 'Объектілер',
    demo: 'Демо-деректер',
    notFound: {
      title: 'Объект табылмады',
      text: 'Мұндай нөмірлі объект жоқ немесе ол сіздің аумағыңыздан тыс.',
      back: 'Объектілер тізіміне',
    },
    header: {
      lastScored: 'Есептеу: {{value}}',
      nextCheck: 'Келесі тексеру: {{value}}',
      notScored: 'Тәуекел әлі есептелмеген',
      recalculate: 'Қайта есептеу',
      createSignal: 'Сигналдық карточка қалыптастыру',
      edit: 'Өңдеу',
      signals: 'Объектінің сигналдық карточкалары',
    },
    passport: {
      title: 'Объект паспорты',
      name: 'Атауы',
      aliases: 'Басқа атаулары',
      address: 'Мекенжайы',
      cadastralNumber: 'Кадастрлық нөмірі',
      landPurpose: 'Жердің нысаналы мақсаты',
      district: 'Аудан',
      coordinates: 'Координаттар',
      plannedCompletion: 'Жоспарлы тапсыру мерзімі',
      forecastCompletion: 'Болжамды тапсыру мерзімі',
      constructionStatus: 'Құрылыс мәртебесі',
      stalledSince: 'Тоқтап тұр, басталған күні',
      priorViolations: 'Бұрынғы бұзушылықтар',
      developer: {
        title: 'Құрылыс салушы',
        bin: 'БСН',
        name: 'Атауы',
        director: 'Басшы',
        founders: 'Құрылтайшылар',
        authorizedCompany: 'Уәкілетті компания',
        phones: 'Телефондар',
        none: 'Құрылыс салушы көрсетілмеген. Оны объектіні өңдеу кезінде таңдауға болады.',
        edit: 'Құрылыс салушыны өңдеу',
      },
    },
  },
};

export default objects;
