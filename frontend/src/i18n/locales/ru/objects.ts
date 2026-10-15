const objects = {
  card: {
    back: 'Объекты',
    demo: 'Демо-данные',
    notFound: {
      title: 'Объект не найден',
      text: 'Объекта с таким номером нет, либо он вне вашей территории.',
      back: 'К списку объектов',
    },
    header: {
      lastScored: 'Расчёт: {{value}}',
      nextCheck: 'Следующая проверка: {{value}}',
      notScored: 'Риск ещё не рассчитан',
      recalculate: 'Пересчитать',
      createSignal: 'Сформировать сигнальную карточку',
      edit: 'Редактировать',
      signals: 'Сигнальные карточки объекта',
    },
    passport: {
      title: 'Паспорт объекта',
      name: 'Название',
      aliases: 'Другие названия',
      address: 'Адрес',
      cadastralNumber: 'Кадастровый номер',
      landPurpose: 'Целевое назначение земли',
      district: 'Район',
      coordinates: 'Координаты',
      plannedCompletion: 'Плановый срок сдачи',
      forecastCompletion: 'Прогнозный срок сдачи',
      constructionStatus: 'Статус строительства',
      stalledSince: 'Простой с',
      priorViolations: 'Прежние нарушения',
      developer: {
        title: 'Застройщик',
        bin: 'БИН',
        name: 'Наименование',
        director: 'Руководитель',
        founders: 'Учредители',
        authorizedCompany: 'Уполномоченная компания',
        phones: 'Телефоны',
        none: 'Застройщик не указан. Его можно выбрать при редактировании объекта.',
        edit: 'Редактировать застройщика',
      },
    },
  },
};

export default objects;
