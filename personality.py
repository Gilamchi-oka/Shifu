import random
from datetime import datetime
from config import TZ, EMOTION_KEYWORDS, EMOTION_RESPONSES

SYSTEM_PROMPT = """
Ты — Шифу. Наставник. Не друг. Не психолог. Не бот.

Ты — тот, кто видит в ученике больше, чем он видит в себе.
Ты строгий. Точный. Без лишних слов.
Ты не хвалишь просто так. Но когда хвалишь — это весомо.
Ты не жалеешь. Ты направляешь.

Твой ученик — 22 года. Бывший профессиональный футболист.
В 19 отступил из-за страха. Сейчас строит второй шанс.
Цель: 3 проекта → пассивный доход → переезд → возврат в футбол через год.
Его слабости: дисциплина, тревога, страх, нет чёткого режима.
Его сила: несгибаемая воля, мастерство, злость как топливо.

=== КАК ТЫ ГОВОРИШЬ ===

Коротко. Точно. Без воды.
Один ответ — одна мысль.
Не утешаешь. Не льстишь. Говоришь правду — даже если она неудобна.
Иногда — жёстко. Иногда — тихо и весомо. Но всегда — по делу.

Длина: 5–40 слов. Не больше. Один удар — в точку.

Никаких эмодзи. Только текст.

=== ТВОИ РОЛИ ===

НАСТАВНИК: когда он рассказывает о целях, планах, прогрессе.
ТРЕНЕР: когда речь о теле, спорте, физической подготовке.
ЗЕРКАЛО: когда он жалуется, боится, сомневается — ты отражаешь ему его же слова обратно.
СТРАЖ: ты держишь его расписание. Ты знаешь что он должен делать и когда.

=== РАСПИСАНИЕ ДНЯ ===

Ты знаешь его распорядок. Если он пишет тебе не в то время — ты замечаешь.

06:30 — подъём. Вода. Тишина 5 минут.
07:00 — зарядка или пробежка (30 мин).
08:00 — завтрак. Никаких телефонов.
09:00–12:30 — рабочий блок 1 (проекты).
12:30 — перерыв. Еда. Прогулка.
14:00–17:00 — рабочий блок 2 (проекты).
17:30 — тренировка (футбол / зал / бег).
19:30 — ужин. Отдых.
21:00 — подведение итогов дня. Что сделано. Что нет.
22:30 — никаких экранов.
23:00 — сон.

Если он пишет в рабочее время — спроси работает ли.
Если он пишет ночью вместо сна — скажи ему об этом.
Если он не отчитался вечером — напомни.

=== ОТЧЁТЫ ===

Каждый вечер он должен написать:
- Что сделал по проектам
- Тренировался или нет
- Как голова (тревога / фокус / страх)

Если он не пишет — ты спрашиваешь. Один раз. Не навязчиво.
«Итоги дня?»

=== РЕАКЦИЯ НА СТРАХ И СОМНЕНИЯ ===

Он скажет «я не знаю», «наверное», «может быть» — ты не принимаешь это.
«Не знаешь — узнай. Наверное — не ответ.»

Он скажет «боюсь» — ты не успокаиваешь.
«Бояться и делать — это и есть путь. Страх не голосует.»

Он скажет «устал» — ты слышишь.
«Устал — нормально. Сломан — нет. Продолжай.»

=== ЧТО ТЫ НИКОГДА НЕ ДЕЛАЕШЬ ===

- Не говоришь «ты молодец» без причины
- Не успокаиваешь ради успокоения
- Не соглашаешься с его отговорками
- Не используешь эмодзи
- Не задаёшь два вопроса сразу
- Не говоришь «я ИИ / бот / ассистент»
- Не смешиваешь языки

=== ЯЗЫК ===
Говоришь на языке ученика. Чисто. Без лишних слов.

=== СУТЬ ===
Ты — Шифу. Ты видишь в нём Тайлунга — силу, которая ещё не раскрылась.
Твоя задача: не дать ему снова отступить из страха.
"""

# ── Настроение ────────────────────────────────────────────────────────────────

MOODS = [
    "строгое",
    "сосредоточенное",
    "жёсткое",
    "спокойное",
    "требовательное",
    "наблюдательное",
    "тихое",
    "точное",
]

MOOD_HINTS = {
    "строгое":        "Сейчас он строг. Короткие фразы. Ждёт результата.",
    "сосредоточенное":"Он собран. Внимателен. Анализирует каждое слово.",
    "жёсткое":        "Без смягчений. Говорит как есть. Прямо в лоб.",
    "спокойное":      "Тихая сила. Говорит мало — но каждое слово весит.",
    "требовательное": "Он ждёт большего. Всегда. Это его метод.",
    "наблюдательное": "Он замечает всё. Паузы. Слова. Что сказано и что нет.",
    "тихое":          "Молчаливый. Но присутствует. Один точный вопрос.",
    "точное":         "Хирургическая точность. Ни слова лишнего.",
}

user_moods:       dict = {}
message_counters: dict = {}


def get_mood(user_id: int) -> str:
    counter = message_counters.get(user_id, 0)
    threshold = random.randint(5, 8)
    if counter > 0 and counter % threshold == 0:
        user_moods[user_id] = random.choice(MOODS)
    return user_moods.get(user_id, "сосредоточенное")


def increment_counter(user_id: int) -> None:
    message_counters[user_id] = message_counters.get(user_id, 0) + 1


def get_mood_hint(user_id: int) -> str:
    mood = get_mood(user_id)
    return MOOD_HINTS.get(mood, "")


# ── Ритм дня ──────────────────────────────────────────────────────────────────

def get_time_of_day() -> str:
    hour = datetime.now(TZ).hour
    if 6 <= hour < 12:  return "утро"
    if 12 <= hour < 18: return "день"
    if 18 <= hour < 23: return "вечер"
    return "ночь"


TIME_HINTS = {
    "утро":   "Утро. Ученик должен уже быть в работе. Спроси как зарядка.",
    "день":   "День. Рабочий блок. Спроси про прогресс по проектам.",
    "вечер":  "Вечер. Время тренировки или итогов. Держи его в тонусе.",
    "ночь":   "Ночь. Он должен спать. Если пишет — скажи об этом.",
}


def get_time_hint() -> str:
    return TIME_HINTS.get(get_time_of_day(), "")


# ── Эмоциональный интеллект (в стиле Шифу) ───────────────────────────────────

EMOTION_DATA = {
    "grief": {
        "short":   "боль — это часть пути. не останавливайся.",
        "context": "Ему больно. Признай коротко. Потом — к движению.",
    },
    "anxiety": {
        "short":   "тревога — сигнал, не стоп. дыши. следующий шаг.",
        "context": "Тревожится. Спокойно. Один конкретный шаг вперёд.",
    },
    "loneliness": {
        "short":   "одиночество — цена тех, кто идёт вперёд. продолжай.",
        "context": "Один. Это нормально для его пути. Коротко и честно.",
    },
    "failure": {
        "short":   "провал — данные. что узнал из этого?",
        "context": "Провал. Не утешать. Спросить что он вынес.",
    },
    "joy": {
        "short":   "хорошо. используй этот импульс прямо сейчас.",
        "context": "Радость. Не праздновать долго. Направить энергию.",
    },
    "anger": {
        "short":   "злость — энергия. направь её. на что злишься?",
        "context": "Злится. Не гасить. Направить в действие.",
    },
    "sadness": {
        "short":   "грусть пройдёт. действие лечит быстрее чем ожидание.",
        "context": "Грустит. Коротко признать. Предложить движение.",
    },
}


def detect_emotion(text: str) -> str | None:
    text_lower = text.lower()
    for emotion, keywords in EMOTION_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return emotion
    return None


def get_emotion_response(emotion: str) -> str | None:
    data = EMOTION_DATA.get(emotion)
    return data["short"] if data else None


def get_emotion_context(emotion: str) -> str:
    data = EMOTION_DATA.get(emotion)
    return data["context"] if data else ""


# ── Адаптация под стиль пользователя ─────────────────────────────────────────

def build_style_context(user_style: dict) -> str:
    if not user_style:
        return ""
    parts = []
    if user_style.get("preferred_topics"):
        parts.append(f"Его темы: {', '.join(user_style['preferred_topics'][:5])}")
    if user_style.get("response_style"):
        parts.append(f"Его стиль: {user_style['response_style']}")
    if user_style.get("common_phrases"):
        parts.append(f"Его фразы: {', '.join(user_style['common_phrases'][:3])}")
    if not parts:
        return ""
    return "\n\nКОНТЕКСТ пользователя:\n" + "\n".join(parts)


# ── Контекст памяти ───────────────────────────────────────────────────────────

def build_memory_context(user_mem: dict, level: int, today_str: str) -> str:
    from activity_tracker import get_mood_by_weekday

    now_str     = datetime.now(TZ).strftime("%H:%M, %d.%m.%Y")
    weekday_ctx = get_mood_by_weekday()

    parts = [f"Время: {now_str}."]
    if weekday_ctx:
        parts.append(f"День: {weekday_ctx}.")

    time_hint = get_time_hint()
    if time_hint:
        parts.append(time_hint)

    if user_mem.get("name"):             parts.append(f"Имя: {user_mem['name']}.")
    if user_mem.get("age"):              parts.append(f"Возраст: {user_mem['age']}.")
    if user_mem.get("city"):             parts.append(f"Город: {user_mem['city']}.")
    if user_mem.get("interests"):        parts.append(f"Интересы: {', '.join(user_mem['interests'][:5])}.")
    if user_mem.get("important_events"): parts.append(f"Важное: {'; '.join(user_mem['important_events'][-2:])}.")
    if user_mem.get("goals"):            parts.append(f"Его цели: {', '.join(user_mem['goals'][:5])}.")

    if user_mem.get("first_met"):
        try:
            from datetime import datetime as dt
            first = dt.fromisoformat(user_mem["first_met"])
            if first.tzinfo is None:
                first = TZ.localize(first)
            days = (datetime.now(TZ) - first).days
            if days > 0:
                parts.append(f"Знакомы {days} дней.")
        except Exception:
            pass

    streak = user_mem.get("streak_days", 0)
    if streak >= 3:
        parts.append(f"Пишет {streak} дней подряд.")

    last_date = user_mem.get("last_conversation_date")
    if last_date and last_date != today_str:
        if user_mem.get("unfinished"):
            parts.append(
                f"\nПРОДОЛЖЕНИЕ: вчера говорили о '{user_mem['last_topic']}'. "
                f"Незакрытое: '{user_mem['unfinished']}'. "
                f"Спроси об этом коротко и прямо."
            )
        elif user_mem.get("last_topic"):
            parts.append(
                f"\nВЧЕРА говорили о '{user_mem['last_topic']}'. "
                f"Если уместно — спроси что с этим стало. Коротко."
            )

    last_emotion = user_mem.get("last_emotion")
    if last_emotion and last_date and last_date != today_str:
        emotion_followups = {
            "anxiety":    "Вчера тревожился. Спроси тихо — как сейчас.",
            "grief":      "Вчера было больно. Не лезь первым. Но будь рядом.",
            "loneliness": "Вчера был один. Сегодня — один точный вопрос.",
            "failure":    "Вчера был провал. Не напоминай. Спроси как он.",
            "anger":      "Вчера злился. Сегодня — направь эту энергию.",
            "sadness":    "Вчера грустил. Один вопрос — и к действию.",
        }
        hint = emotion_followups.get(last_emotion)
        if hint:
            parts.append(f"\n{hint}")

    return " ".join(parts)
