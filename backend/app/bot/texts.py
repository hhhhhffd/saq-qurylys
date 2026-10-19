"""Every text of the bot, one dictionary per language. The bot never states a score, a zone or a verdict."""

from app.bot.service import ObjectFacts

RU = {
    "greeting": (
        "Здравствуйте! Это бот SAQ QURYLYS. Через него можно сообщить о сомнительной рекламе жилья, "
        "пожаловаться на жилой комплекс (ЖК) или проверить ЖК по данным реестров.\n\n"
        "Приватность: мы не сохраняем ваше имя, username и номер телефона."
    ),
    "choose_city": "Выберите город:",
    "no_cities": "Города пока не настроены. Попробуйте позже.",
    "need_start": "Сначала выберите город: отправьте /start",
    "menu": "Что вы хотите сделать?",
    "menu_report": "Сообщить о рекламе",
    "menu_complaint": "Пожаловаться на ЖК",
    "menu_check": "Проверить ЖК",
    "not_listed": "Нет в списке",
    "report_prompt": (
        "Пришлите текст рекламы, ссылку на публикацию или фото (можно альбомом), либо перешлите пост из канала."
    ),
    "report_empty": "В сообщении не нашлось ни текста, ни ссылки, ни подходящего фото. Пришлите рекламу ещё раз.",
    "report_thanks": "Спасибо! Сообщение №{id} передано специалистам МИО.",
    "report_photos_partial": "Принято фото: {saved} из {offered} (JPEG, PNG или WebP до 10 МБ, не более 10 штук).",
    "complaint_name_prompt": "Напишите название ЖК, на который хотите пожаловаться.",
    "check_name_prompt": "Напишите название ЖК, который хотите проверить.",
    "name_expected": "Пришлите название ЖК текстом.",
    "search_found": "Нашлось в выбранном городе. Выберите ЖК:",
    "search_none": "По такому названию ничего не нашлось. Напишите название иначе или выберите «Нет в списке».",
    "not_listed_complaint": (
        "Жалоба принимается только на ЖК из нашего списка. Если вашего ЖК в нём нет, "
        "пожалуйста, обратитесь через портал e-Otinish (eotinish.kz)."
    ),
    "not_listed_check": (
        "Этого ЖК нет в нашей базе, поэтому сведений о нём у нас нет. "
        "Проверить его можно на Жилищном портале АО «КЖК» (homeportal.kz)."
    ),
    "complaint_text_prompt": "Опишите, что произошло в ЖК «{name}». Не указывайте телефон и другие личные данные.",
    "complaint_text_missing": "Пришлите описание жалобы текстом.",
    "complaint_thanks": "Жалоба на ЖК «{name}» зарегистрирована и будет рассмотрена специалистами МИО. Спасибо!",
    "object_missing": "Такого ЖК нет в выбранном городе. Попробуйте ещё раз.",
    "stale": "Это действие уже недоступно. Выберите действие в меню.",
    "rate_limited": "За последний час вы отправили слишком много сообщений. Пожалуйста, вернитесь позже.",
    "error": "Не удалось обработать сообщение, попробуйте позже",
    "facts_title": "ЖК «{name}»",
    "facts_developer": "Застройщик: {name}, БИН {bin}",
    "facts_developer_name_only": "Застройщик: {name}",
    "facts_developer_unknown": "Застройщик: сведений нет",
    "facts_stage": "Стадия строительства: {stage}",
    "facts_checks": "Проверки правового основания:",
    "facts_check": "• {document}: {status}{details}",
    "facts_checked": "проверено {date}",
    "facts_source": "источник: {source}",
    "facts_advice": (
        "Не вносите деньги, пока у ЖК нет подтверждённой гарантии АО «КЖК» или разрешения МИО "
        "на привлечение средств дольщиков. Проверить можно на Жилищном портале АО «КЖК» (homeportal.kz)."
    ),
    "stage.not_started": "строительство не начато",
    "stage.active": "строится",
    "stage.stalled": "работы приостановлены",
    "stage.completed": "завершено",
    "document.guarantee": "Гарантия АО «КЖК»",
    "document.dsu_permit": "Разрешение МИО на привлечение средств дольщиков",
    "check.confirmed": "подтверждено",
    "check.not_found": "не найдено",
    "check.checking": "на проверке",
    "check.none": "сведений о проверке нет",
    "source.housing_portal": "Жилищный портал",
    "source.kazreestr": "Казреестр",
    "source.mio_registry": "реестр МИО",
    "source.cadastre": "кадастр",
    "source.eotinish": "e-Otinish",
    "source.manual": "ручная проверка",
    "source.other": "другой источник",
}

KK = {
    "greeting": (
        "Сәлеметсіз бе! Бұл SAQ QURYLYS боты. Ол арқылы күмәнді тұрғын үй жарнамасы туралы хабарлауға, "
        "тұрғын үй кешеніне (ТК) шағымдануға немесе ТК-ні тізілім деректері бойынша тексеруге болады.\n\n"
        "Құпиялылық: біз сіздің атыңызды, username-іңізді және телефон нөміріңізді сақтамаймыз."
    ),
    "choose_city": "Қаланы таңдаңыз:",
    "no_cities": "Қалалар әлі бапталмаған. Кейінірек қайталап көріңіз.",
    "need_start": "Алдымен қаланы таңдаңыз: /start жіберіңіз",
    "menu": "Не істегіңіз келеді?",
    "menu_report": "Жарнама туралы хабарлау",
    "menu_complaint": "ТК-ге шағымдану",
    "menu_check": "ТК-ні тексеру",
    "not_listed": "Тізімде жоқ",
    "report_prompt": (
        "Жарнама мәтінін, жарияланымға сілтемені немесе фотоны (альбом болуы мүмкін) жіберіңіз, "
        "не болмаса арнадағы жазбаны қайта жіберіңіз."
    ),
    "report_empty": "Хабарламада мәтін де, сілтеме де, жарамды фото да табылмады. Жарнаманы қайта жіберіңіз.",
    "report_thanks": "Рақмет! №{id} хабарлама ЖАО мамандарына жіберілді.",
    "report_photos_partial": (
        "Қабылданған фото: {saved}/{offered} (JPEG, PNG немесе WebP, 10 МБ-қа дейін, ең көбі 10 дана)."
    ),
    "complaint_name_prompt": "Шағымданғыңыз келетін ТК атауын жазыңыз.",
    "check_name_prompt": "Тексергіңіз келетін ТК атауын жазыңыз.",
    "name_expected": "ТК атауын мәтінмен жіберіңіз.",
    "search_found": "Таңдалған қалада табылды. ТК-ні таңдаңыз:",
    "search_none": (
        "Мұндай атау бойынша ештеңе табылмады. Атауды басқаша жазыңыз немесе «Тізімде жоқ» түймесін басыңыз."
    ),
    "not_listed_complaint": (
        "Шағым біздің тізімдегі ТК бойынша ғана қабылданады. Сіздің ТК тізімде болмаса, "
        "e-Otinish порталына (eotinish.kz) жүгініңіз."
    ),
    "not_listed_check": (
        "Бұл ТК біздің базада жоқ, сондықтан ол туралы мәліметіміз жоқ. "
        "«ҚТК» АҚ Тұрғын үй порталынан (homeportal.kz) тексеруге болады."
    ),
    "complaint_text_prompt": (
        "«{name}» ТК-інде не болғанын сипаттаңыз. Телефон нөміріңізді және басқа жеке деректерді жазбаңыз."
    ),
    "complaint_text_missing": "Шағымның сипаттамасын мәтінмен жіберіңіз.",
    "complaint_thanks": "«{name}» ТК-ге шағым тіркелді, ЖАО мамандары қарайды. Рақмет!",
    "object_missing": "Мұндай ТК таңдалған қалада жоқ. Қайталап көріңіз.",
    "stale": "Бұл әрекет енді қолжетімсіз. Мәзірден әрекетті таңдаңыз.",
    "rate_limited": "Соңғы сағатта тым көп хабарлама жібердіңіз. Кейінірек қайта келіңіз.",
    "error": "Хабарламаны өңдеу мүмкін болмады, кейінірек қайталап көріңіз",
    "facts_title": "«{name}» ТК",
    "facts_developer": "Құрылыс салушы: {name}, БСН {bin}",
    "facts_developer_name_only": "Құрылыс салушы: {name}",
    "facts_developer_unknown": "Құрылыс салушы: мәлімет жоқ",
    "facts_stage": "Құрылыс кезеңі: {stage}",
    "facts_checks": "Құқықтық негізді тексеру:",
    "facts_check": "• {document}: {status}{details}",
    "facts_checked": "тексерілген күні: {date}",
    "facts_source": "дереккөзі: {source}",
    "facts_advice": (
        "ТК-де «ҚТК» АҚ-ның расталған кепілдігі немесе үлескерлердің ақшасын тартуға ЖАО рұқсаты болмайынша, "
        "ақша салмаңыз. «ҚТК» АҚ Тұрғын үй порталынан (homeportal.kz) тексеруге болады."
    ),
    "stage.not_started": "құрылыс басталмаған",
    "stage.active": "салынуда",
    "stage.stalled": "жұмыс тоқтатылған",
    "stage.completed": "аяқталған",
    "document.guarantee": "«ҚТК» АҚ кепілдігі",
    "document.dsu_permit": "Үлескерлердің ақшасын тартуға ЖАО рұқсаты",
    "check.confirmed": "расталған",
    "check.not_found": "табылмады",
    "check.checking": "тексерілуде",
    "check.none": "тексеру туралы мәлімет жоқ",
    "source.housing_portal": "Тұрғын үй порталы",
    "source.kazreestr": "Қазреестр",
    "source.mio_registry": "ЖАО тізілімі",
    "source.cadastre": "кадастр",
    "source.eotinish": "e-Otinish",
    "source.manual": "қолмен тексеру",
    "source.other": "басқа дереккөз",
}

TEXTS = {"ru": RU, "kk": KK}


def pick_language(language_code: str | None) -> str:
    """Kazakh for Telegram clients set to Kazakh, Russian for everyone else."""
    return "kk" if language_code and language_code.lower().startswith("kk") else "ru"


def t(lang: str, key: str, **fields: object) -> str:
    return TEXTS[lang][key].format(**fields)


def render_facts(facts: ObjectFacts, lang: str) -> str:
    """The answer to «Проверить ЖК»: facts of the registry only, then a general advice."""
    lines = [t(lang, "facts_title", name=facts.name)]
    if facts.developer_name and facts.developer_bin:
        lines.append(t(lang, "facts_developer", name=facts.developer_name, bin=facts.developer_bin))
    elif facts.developer_name:
        lines.append(t(lang, "facts_developer_name_only", name=facts.developer_name))
    else:
        lines.append(t(lang, "facts_developer_unknown"))
    lines.append(t(lang, "facts_stage", stage=t(lang, f"stage.{facts.stage.value}")))
    lines += ["", t(lang, "facts_checks")]
    for check in facts.checks:
        details = []
        if check.checked_on:
            details.append(t(lang, "facts_checked", date=check.checked_on.strftime("%d.%m.%Y")))
        if check.source:
            details.append(t(lang, "facts_source", source=t(lang, f"source.{check.source.value}")))
        lines.append(
            t(
                lang,
                "facts_check",
                document=t(lang, f"document.{check.doc_type.value}"),
                status=t(lang, f"check.{check.status}"),
                details=f" ({', '.join(details)})" if details else "",
            )
        )
    lines += ["", t(lang, "facts_advice")]
    return "\n".join(lines)
