// NOTE: Kazakh (kk) translations need native-speaker review.
import type ru from '../ru/activity';

const activity: typeof ru = {
  region: 'Оқиғалардың тірі лентасы',
  title: {
    adCitizen: 'Азаматтың хабарламасы',
    adCollector: 'Жаңа жарияланым',
    adStaff: 'Жарияланым қосылды',
    signalCreated: 'Жаңа сигналдық карточка',
    signalSent: 'Карточка жіберілді',
  },
  score: {
    up: 'Тәуекел бағасы өсті',
    down: 'Тәуекел бағасы төмендеді',
    zone: 'Аймақ: {{from}} → {{to}}',
    announce: 'Балл {{from}} мәнінен {{to}} мәніне өзгерді. Аймақ: {{zone}}',
  },
};

export default activity;
