// NOTE: Kazakh (kk) translations need native-speaker review.
import type ru from '../ru/map';

const map: typeof ru = {
  title: 'Объектілер картасы',
  links: {
    signals: 'Сигналдық карточкаларды ашу',
    ads: 'Жарнама лентасы',
  },
  counters: {
    label: 'Аймақтар бойынша объектілер саны. Картада және тізімде тек таңдалған аймақты қалдыру үшін оны басыңыз',
    unscored: 'Бағаланбаған: {{count}}',
  },
  list: {
    title: 'Объектілер тәуекелі кему ретімен',
    empty: 'Объектілер табылмады',
    emptyHint: 'Аумақты, ауданды немесе аймақты өзгертіп көріңіз',
    showMore: 'Тағы көрсету ({{count}})',
  },
  map: {
    label: 'Объектілер картасы',
    unavailable: 'Карта қолжетімсіз: браузер WebGL-ді қолдамайды немесе ол өшірілген. Объектілер тізімі жұмыс істейді.',
    withoutCoordinates: 'Координаттары жоқ, картада көрсетілмеген: {{count}}',
    popupScore: 'Балл: {{score}}',
    zoomIn: 'Жақындату',
    zoomOut: 'Алыстату',
    toggleAttribution: 'Карта деректерінің көздері',
    mapFeedback: 'Картадағы қате туралы хабарлау',
  },
};

export default map;
