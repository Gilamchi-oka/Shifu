"""
tools.py — команды, задачи, таймеры, бюджет, обучение языка,
           Wikipedia, новости, курсы валют, погода
"""

import json, os, re, requests
from datetime import datetime, timedelta
from config import TZ, TASKS_FILE, WEATHER_KEY

# ═══════════════════════════════════════════════════════════════════════════════
# ЗАДАЧИ / НАПОМИНАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════
#
# Два типа задач в одном файле kamilla_tasks.json:
#
# 1) РАЗОВАЯ задача (старый формат, не трогаем):
#    {"user_id":.., "text":.., "remind_at": "...", "done": False}
#    Срабатывает один раз через N минут от момента создания.
#
# 2) ЕЖЕДНЕВНАЯ задача (новый формат):
#    {"user_id":.., "text":.., "time": "09:00", "repeat": "daily",
#     "done": False, "last_sent_date": None}
#    Срабатывает каждый день в указанное время. После срабатывания
#    "done" не остаётся True навсегда — на следующий день она снова активна.
#    last_sent_date хранит дату (YYYY-MM-DD), когда напоминание было
#    отправлено последний раз — это и защищает от повторной отправки
#    в тот же день и от "вечной потери" задачи.

def load_tasks() -> list:
    if not os.path.exists(TASKS_FILE):
        return []
    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return []
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"⚠️ {TASKS_FILE} повреждён ({e}), сброс")
        import shutil
        shutil.copy(TASKS_FILE, TASKS_FILE + ".broken")
        save_tasks([])
        return []

def save_tasks(tasks: list):
    import tempfile
    dir_name = os.path.dirname(TASKS_FILE) or "."
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=dir_name,
        delete=False, suffix=".tmp"
    ) as tmp:
        json.dump(tasks, tmp, ensure_ascii=False, indent=2)
        tmp_path = tmp.name
    os.replace(tmp_path, TASKS_FILE)
def clear_user_tasks(user_id: int):
    tasks = [t for t in load_tasks() if t["user_id"] != user_id]
    save_tasks(tasks)

def add_task(user_id: int, text: str, minutes: int):
    """Разовое напоминание через N минут от текущего момента."""
    tasks     = load_tasks()
    remind_at = datetime.now(TZ) + timedelta(minutes=minutes)
    tasks.append({
        "user_id":   user_id,
        "text":      text,
        "remind_at": remind_at.isoformat(),
        "done":      False,
    })
    save_tasks(tasks)

def _normalize_time(time_str: str) -> str | None:
    """Принимает '9:00', '09:00', '9', '900' → возвращает 'HH:MM' или None."""
    time_str = time_str.strip()
    m = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}"
        return None
    m = re.match(r'^(\d{1,2})$', time_str)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            return f"{h:02d}:00"
    return None

def add_daily_task(user_id: int, text: str, time_str: str) -> str:
    """
    Добавляет ЕЖЕДНЕВНУЮ задачу на фиксированное время (утро/обед/вечер и т.п.).
    Если задача с таким же текстом+временем у юзера уже есть — не дублирует.
    """
    normalized = _normalize_time(time_str)
    if not normalized:
        return None

    tasks = load_tasks()
    for t in tasks:
        if (t.get("user_id") == user_id and t.get("repeat") == "daily"
                and t.get("text") == text and t.get("time") == normalized):
            return normalized  # уже есть такая — не дублируем

    tasks.append({
        "user_id":       user_id,
        "text":          text,
        "time":          normalized,
        "repeat":        "daily",
        "done":          False,
        "last_sent_date": None,
    })
    save_tasks(tasks)
    return normalized

def get_daily_tasks(user_id: int) -> list:
    return [
        t for t in load_tasks()
        if t.get("user_id") == user_id and t.get("repeat") == "daily"
    ]

def remove_daily_task(user_id: int, text: str) -> bool:
    """Удаляет ежедневную задачу по тексту (точное совпадение или подстрока)."""
    tasks = load_tasks()
    text_low = text.lower().strip()
    before = len(tasks)
    tasks = [
        t for t in tasks
        if not (
            t.get("user_id") == user_id
            and t.get("repeat") == "daily"
            and text_low in t.get("text", "").lower()
        )
    ]
    save_tasks(tasks)
    return len(tasks) < before

# ═══════════════════════════════════════════════════════════════════════════════
# ВРЕМЯ / ТАЙМЕР / СЕКУНДОМЕР
# ═══════════════════════════════════════════════════════════════════════════════

# Хранит активные секундомеры: user_id → datetime старта
_stopwatches: dict = {}

def get_current_time() -> str:
    now = datetime.now(TZ)
    weekdays = ["понедельник","вторник","среда","четверг","пятница","суббота","воскресенье"]
    months   = ["января","февраля","марта","апреля","мая","июня",
                "июля","августа","сентября","октября","ноября","декабря"]
    wd  = weekdays[now.weekday()]
    mon = months[now.month - 1]
    return f"{now.strftime('%H:%M')}, {wd}, {now.day} {mon} {now.year}"

def stopwatch_start(user_id: int) -> str:
    _stopwatches[user_id] = datetime.now(TZ)
    return "секундомер запущен ⏱"

def stopwatch_stop(user_id: int) -> str:
    start = _stopwatches.pop(user_id, None)
    if not start:
        return "секундомер не был запущен"
    delta   = datetime.now(TZ) - start
    total_s = int(delta.total_seconds())
    h, rem  = divmod(total_s, 3600)
    m, s    = divmod(rem, 60)
    if h:
        return f"прошло {h}ч {m}мин {s}сек ⏱"
    elif m:
        return f"прошло {m}мин {s}сек ⏱"
    else:
        return f"прошло {s}сек ⏱"

def stopwatch_status(user_id: int) -> str:
    start = _stopwatches.get(user_id)
    if not start:
        return "секундомер не запущен"
    delta   = datetime.now(TZ) - start
    total_s = int(delta.total_seconds())
    h, rem  = divmod(total_s, 3600)
    m, s    = divmod(rem, 60)
    if h:
        return f"идёт {h}ч {m}мин {s}сек ⏱"
    elif m:
        return f"идёт {m}мин {s}сек ⏱"
    else:
        return f"идёт {s}сек ⏱"

# ═══════════════════════════════════════════════════════════════════════════════
# БЮДЖЕТ
# ═══════════════════════════════════════════════════════════════════════════════

BUDGET_FILE = "kamilla_budget.json"

EXPENSE_CATEGORIES = {
    "еда":        ["еда", "обед", "ужин", "завтрак", "кафе", "ресторан", "фаст", "пицца", "суши", "шаурма", "продукты"],
    "транспорт":  ["такси", "автобус", "метро", "бензин", "uber", "yandex go", "дорога"],
    "развлечения":["кино", "игра", "концерт", "клуб", "бар", "развлечен"],
    "здоровье":   ["аптека", "врач", "лекарство", "больница", "клиника"],
    "одежда":     ["одежда", "кроссовки", "куртка", "штаны", "рубашка", "магазин"],
    "связь":      ["интернет", "телефон", "симка", "пополнил"],
    "прочее":     [],
}

def _detect_category(text: str) -> str:
    text_lower = text.lower()
    for cat, keywords in EXPENSE_CATEGORIES.items():
        if any(kw in text_lower for kw in keywords):
            return cat
    return "прочее"

def _load_budget() -> dict:
    if os.path.exists(BUDGET_FILE):
        with open(BUDGET_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save_budget(data: dict):
    with open(BUDGET_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_expense(user_id: int, amount: float, description: str) -> str:
    data     = _load_budget()
    key      = str(user_id)
    now      = datetime.now(TZ)
    date_str = now.strftime("%Y-%m-%d")
    category = _detect_category(description)

    if key not in data:
        data[key] = {"expenses": []}

    data[key]["expenses"].append({
        "date":        date_str,
        "amount":      amount,
        "description": description,
        "category":    category,
        "time":        now.strftime("%H:%M"),
    })

    _save_budget(data)

    # Форматируем сумму красиво
    amount_str = f"{amount:,.0f}".replace(",", " ")
    return f"записала: {description} — {amount_str} сум ({category})"

def get_expenses_today(user_id: int) -> str:
    data     = _load_budget()
    key      = str(user_id)
    today    = datetime.now(TZ).strftime("%Y-%m-%d")
    expenses = [e for e in data.get(key, {}).get("expenses", []) if e["date"] == today]

    if not expenses:
        return "сегодня расходов не записано"

    total = sum(e["amount"] for e in expenses)
    lines = [f"📊 расходы за сегодня:"]
    by_cat: dict = {}
    for e in expenses:
        cat = e["category"]
        by_cat[cat] = by_cat.get(cat, 0) + e["amount"]

    for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
        amt_str = f"{amt:,.0f}".replace(",", " ")
        lines.append(f"  {cat}: {amt_str} сум")

    total_str = f"{total:,.0f}".replace(",", " ")
    lines.append(f"итого: {total_str} сум")
    return "\n".join(lines)

def get_expenses_month(user_id: int) -> str:
    data      = _load_budget()
    key       = str(user_id)
    now       = datetime.now(TZ)
    month_str = now.strftime("%Y-%m")
    expenses  = [
        e for e in data.get(key, {}).get("expenses", [])
        if e["date"].startswith(month_str)
    ]

    if not expenses:
        return "в этом месяце расходов нет"

    total = sum(e["amount"] for e in expenses)
    by_cat: dict = {}
    for e in expenses:
        cat = e["category"]
        by_cat[cat] = by_cat.get(cat, 0) + e["amount"]

    months_ru = ["","января","февраля","марта","апреля","мая","июня",
                 "июля","августа","сентября","октября","ноября","декабря"]
    month_name = months_ru[now.month]

    lines = [f"📊 расходы за {month_name}:"]
    for cat, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
        pct     = amt / total * 100
        amt_str = f"{amt:,.0f}".replace(",", " ")
        lines.append(f"  {cat}: {amt_str} сум ({pct:.0f}%)")

    total_str = f"{total:,.0f}".replace(",", " ")
    lines.append(f"итого: {total_str} сум")
    return "\n".join(lines)

def get_daily_budget_summary(user_id: int) -> str | None:
    """Вызывается вечером — возвращает сводку если были расходы"""
    data     = _load_budget()
    key      = str(user_id)
    today    = datetime.now(TZ).strftime("%Y-%m-%d")
    expenses = [e for e in data.get(key, {}).get("expenses", []) if e["date"] == today]

    if not expenses:
        return None

    total     = sum(e["amount"] for e in expenses)
    total_str = f"{total:,.0f}".replace(",", " ")
    count     = len(expenses)
    return f"кстати, сегодня потратил {total_str} сум ({count} трат). хочешь подробнее?"

# ═══════════════════════════════════════════════════════════════════════════════
# ОБУЧЕНИЕ ЯЗЫКА
# ═══════════════════════════════════════════════════════════════════════════════

LANG_FILE = "kamilla_language.json"

# Встроенный словарь для старта (английский)
ENGLISH_WORDS = [
    {"word": "apple",       "translation": "яблоко",     "example": "I eat an apple every day"},
    {"word": "beautiful",   "translation": "красивый",   "example": "The view is beautiful"},
    {"word": "challenge",   "translation": "вызов",      "example": "This is a challenge for me"},
    {"word": "dream",       "translation": "мечта",      "example": "Follow your dream"},
    {"word": "effort",      "translation": "усилие",     "example": "It takes effort to succeed"},
    {"word": "freedom",     "translation": "свобода",    "example": "Freedom is precious"},
    {"word": "grateful",    "translation": "благодарный","example": "I am grateful for this"},
    {"word": "honest",      "translation": "честный",    "example": "Be honest with yourself"},
    {"word": "improve",     "translation": "улучшать",   "example": "I want to improve my skills"},
    {"word": "journey",     "translation": "путешествие","example": "Life is a journey"},
    {"word": "kindness",    "translation": "доброта",    "example": "Kindness costs nothing"},
    {"word": "lonely",      "translation": "одинокий",   "example": "Sometimes I feel lonely"},
    {"word": "memory",      "translation": "память",     "example": "This is a good memory"},
    {"word": "nature",      "translation": "природа",    "example": "I love nature"},
    {"word": "opportunity", "translation": "возможность","example": "This is a great opportunity"},
    {"word": "patience",    "translation": "терпение",   "example": "Patience is a virtue"},
    {"word": "quality",     "translation": "качество",   "example": "Quality over quantity"},
    {"word": "respect",     "translation": "уважение",   "example": "Respect yourself first"},
    {"word": "strength",    "translation": "сила",       "example": "Find your inner strength"},
    {"word": "trust",       "translation": "доверие",    "example": "Trust takes time to build"},
    {"word": "unique",      "translation": "уникальный", "example": "You are unique"},
    {"word": "valuable",    "translation": "ценный",     "example": "Time is valuable"},
    {"word": "wisdom",      "translation": "мудрость",   "example": "Wisdom comes with experience"},
    {"word": "brave",       "translation": "храбрый",    "example": "Be brave enough to try"},
    {"word": "curious",     "translation": "любопытный", "example": "Stay curious always"},
]

def _load_lang(user_id: int) -> dict:
    data = {}
    if os.path.exists(LANG_FILE):
        with open(LANG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    return data.get(str(user_id), {
        "active":       False,
        "language":     "english",
        "current_word": None,
        "score":        0,
        "total":        0,
        "streak":       0,
        "learned":      [],       # выученные слова
        "failed":       [],       # проблемные слова
        "session_score": 0,
        "session_total": 0,
    })

def _save_lang(user_id: int, state: dict):
    data = {}
    if os.path.exists(LANG_FILE):
        with open(LANG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    data[str(user_id)] = state
    with open(LANG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def lang_start(user_id: int, language: str = "english") -> str:
    state = _load_lang(user_id)
    state["active"]        = True
    state["language"]      = language
    state["session_score"] = 0
    state["session_total"] = 0
    _save_lang(user_id, state)
    word_msg = lang_next_word(user_id)
    return (
        f"режим препода включён 📚 учим {language}\n"
        f"буду давать слово — ты пишешь перевод. поехали\n\n"
        f"{word_msg}"
    )

def lang_stop(user_id: int) -> str:
    state = _load_lang(user_id)
    score = state.get("session_score", 0)
    total = state.get("session_total", 0)
    state["active"] = False
    _save_lang(user_id, state)
    if total == 0:
        return "занятие завершено. до следующего раза 📚"
    pct = score / total * 100
    if pct >= 80:
        grade = "отлично 🔥"
    elif pct >= 60:
        grade = "неплохо 👍"
    else:
        grade = "надо потренироваться ещё"
    return f"занятие окончено. {score}/{total} правильно — {grade}"

def lang_next_word(user_id: int) -> str:
    import random
    state   = _load_lang(user_id)
    learned = set(state.get("learned", []))

    # Сначала повторяем проблемные слова
    failed = state.get("failed", [])
    if failed and random.random() > 0.5:
        entry = random.choice([w for w in ENGLISH_WORDS if w["word"] in failed])
    else:
        # Берём слово которое ещё не выучено
        available = [w for w in ENGLISH_WORDS if w["word"] not in learned]
        if not available:
            available = ENGLISH_WORDS  # прошли все — начинаем заново
        entry = random.choice(available)

    state["current_word"] = entry["word"]
    _save_lang(user_id, state)

    return f"переведи: **{entry['word']}**"

def lang_check_answer(user_id: int, answer: str) -> tuple[bool, str]:
    """Проверяет ответ. Возвращает (правильно?, текст реакции)"""
    state   = _load_lang(user_id)
    current = state.get("current_word")
    if not current:
        return False, ""

    entry = next((w for w in ENGLISH_WORDS if w["word"] == current), None)
    if not entry:
        return False, ""

    correct_translation = entry["translation"].lower().strip()
    user_answer         = answer.lower().strip()

    # Засчитываем если совпадает или очень близко
    is_correct = (
        user_answer == correct_translation or
        user_answer in correct_translation or
        correct_translation in user_answer
    )

    state["total"]         = state.get("total", 0) + 1
    state["session_total"] = state.get("session_total", 0) + 1

    if is_correct:
        state["score"]         = state.get("score", 0) + 1
        state["session_score"] = state.get("session_score", 0) + 1
        state["streak"]        = state.get("streak", 0) + 1

        # Добавляем в выученные если отвечал правильно 2+ раз
        learned = state.get("learned", [])
        if current not in learned:
            learned.append(current)
            state["learned"] = learned

        # Убираем из проблемных
        failed = state.get("failed", [])
        if current in failed:
            failed.remove(current)
            state["failed"] = failed

        streak = state["streak"]
        if streak >= 5:
            reaction = f"правильно! 🔥 {streak} подряд, ты машина"
        elif streak >= 3:
            reaction = f"да! {streak} подряд 👏"
        else:
            reaction = _random_correct()

        reaction += f"\n_{entry['word']}_ — {entry['translation']}"
        reaction += f"\n\"{entry['example']}\""

    else:
        state["streak"] = 0
        failed = state.get("failed", [])
        if current not in failed:
            failed.append(current)
            state["failed"] = failed

        reaction = (
            f"не совсем. правильно: **{entry['translation']}**\n"
            f"_{entry['word']}_ — {entry['translation']}\n"
            f"\"{entry['example']}\""
        )

    _save_lang(user_id, state)
    return is_correct, reaction

def _random_correct() -> str:
    import random
    variants = [
        "правильно ✓",
        "да, верно",
        "точно",
        "молодец",
        "хорошо",
        "правильно, запомни",
    ]
    return random.choice(variants)

def lang_stats(user_id: int) -> str:
    state   = _load_lang(user_id)
    total   = state.get("total", 0)
    score   = state.get("score", 0)
    learned = len(state.get("learned", []))
    streak  = state.get("streak", 0)
    if total == 0:
        return "ещё не начинали учиться"
    pct = score / total * 100
    return (
        f"📚 прогресс:\n"
        f"  правильных ответов: {score}/{total} ({pct:.0f}%)\n"
        f"  выучено слов: {learned}/{len(ENGLISH_WORDS)}\n"
        f"  серия правильных: {streak}"
    )

def is_lang_active(user_id: int) -> bool:
    return _load_lang(user_id).get("active", False)

# ═══════════════════════════════════════════════════════════════════════════════
# WIKIPEDIA
# ═══════════════════════════════════════════════════════════════════════════════

def needs_wiki(text: str) -> str | None:
    patterns = [
        r"кто такой (.+)", r"что такое (.+)", r"расскажи про (.+)",
        r"кто такая (.+)", r"что такая (.+)", r"что значит (.+)",
    ]
    for pat in patterns:
        m = re.search(pat, text.lower())
        if m:
            return m.group(1).strip()
    return None

def search_wikipedia(query: str) -> str | None:
    try:
        url    = "https://ru.wikipedia.org/api/rest_v1/page/summary/" + requests.utils.quote(query)
        r      = requests.get(url, timeout=5)
        if r.status_code == 200:
            data = r.json()
            extract = data.get("extract", "")
            if extract:
                # Возвращаем первые 2 предложения
                sentences = re.split(r'(?<=[.!?])\s+', extract)
                return " ".join(sentences[:2])
    except Exception as e:
        print(f"Wiki error: {e}")
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# НОВОСТИ
# ═══════════════════════════════════════════════════════════════════════════════

def needs_news(text: str) -> str | None:
    triggers = ["что нового", "новости", "что случилось", "что происходит"]
    text_lower = text.lower()
    for t in triggers:
        if t in text_lower:
            # Пробуем извлечь тему
            after = text_lower.split(t)[-1].strip()
            return after if len(after) > 2 else "главные"
    return None

def get_news(topic: str) -> list[str]:
    try:
        url = f"https://newsapi.org/v2/everything?q={requests.utils.quote(topic)}&language=ru&pageSize=3&sortBy=publishedAt"
        r   = requests.get(url, timeout=5)
        if r.status_code == 200:
            articles = r.json().get("articles", [])
            return [a["title"] for a in articles if a.get("title")][:3]
    except Exception as e:
        print(f"News error: {e}")
    return []

# ═══════════════════════════════════════════════════════════════════════════════
# КУРСЫ ВАЛЮТ / КОНВЕРТАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════════

def get_exchange_rate(currency: str) -> str:
    try:
        url = f"https://api.exchangerate-api.com/v4/latest/USD"
        r   = requests.get(url, timeout=5)
        if r.status_code == 200:
            rates = r.json().get("rates", {})
            uzs   = rates.get("UZS", 0)
            eur   = rates.get("EUR", 0)
            rub   = rates.get("RUB", 0)
            cur   = currency.upper()
            if cur in ("USD", "ДОЛЛАР", "DOLLAR"):
                return f"1 USD = {uzs:,.0f} сум"
            elif cur in ("EUR", "ЕВРО", "EURO"):
                usd_eur = 1 / eur if eur else 0
                return f"1 EUR = {uzs * usd_eur:,.0f} сум"
            elif cur in ("RUB", "РУБЛЬ", "РУБЛЕЙ"):
                usd_rub = 1 / rub if rub else 0
                return f"1 RUB = {uzs * usd_rub:,.0f} сум"
            return f"не знаю курс {currency}"
    except Exception as e:
        print(f"Rate error: {e}")
    return "не могу получить курс сейчас"

def convert_currency(amount: float, from_cur: str, to_cur: str) -> str:
    try:
        url = "https://api.exchangerate-api.com/v4/latest/USD"
        r   = requests.get(url, timeout=5)
        if r.status_code == 200:
            rates     = r.json().get("rates", {})
            from_rate = rates.get(from_cur.upper(), 1)
            to_rate   = rates.get(to_cur.upper(), 1)
            result    = amount / from_rate * to_rate
            return f"{amount:,.0f} {from_cur.upper()} = {result:,.0f} {to_cur.upper()}"
    except Exception as e:
        print(f"Convert error: {e}")
    return "не могу конвертировать сейчас"

# ═══════════════════════════════════════════════════════════════════════════════
# ПОГОДА
# ═══════════════════════════════════════════════════════════════════════════════

def get_weather(city: str) -> str:
    if not WEATHER_KEY:
        return "ключ погоды не настроен"
    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?q={requests.utils.quote(city)}&appid={WEATHER_KEY}"
            f"&units=metric&lang=ru"
        )
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            data  = r.json()
            temp  = data["main"]["temp"]
            feels = data["main"]["feels_like"]
            desc  = data["weather"][0]["description"]
            wind  = data["wind"]["speed"]
            return (
                f"{city}: {temp:.0f}°C, {desc}\n"
                f"ощущается как {feels:.0f}°C, ветер {wind} м/с"
            )
        return f"не нашла город {city}"
    except Exception as e:
        print(f"Weather error: {e}")
        return "не могу получить погоду"

# ═══════════════════════════════════════════════════════════════════════════════
# ПАРСИНГ КОМАНД ИЗ ОТВЕТА AI
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_minutes(text: str) -> int | None:
    """Парсит '5 минут', '1 час', '30 сек' → минуты"""
    text = text.lower().strip()
    patterns = [
        (r'(\d+)\s*час',    lambda m: int(m.group(1)) * 60),
        (r'(\d+)\s*мин',    lambda m: int(m.group(1))),
        (r'(\d+)\s*сек',    lambda m: max(1, int(m.group(1)) // 60)),
        (r'(\d+)',          lambda m: int(m.group(1))),
    ]
    for pat, fn in patterns:
        m = re.search(pat, text)
        if m:
            return fn(m)
    return None

def _parse_amount(text: str) -> float | None:
    """Парсит сумму из текста: '50к', '50000', '50 тысяч'"""
    text = text.lower().replace(" ", "")
    m = re.search(r'(\d+(?:\.\d+)?)(к|k|тыс)?', text)
    if m:
        num = float(m.group(1))
        if m.group(2):
            num *= 1000
        return num
    return None

def parse_commands(text: str, user_id: int) -> tuple[str, list]:
    """
    Парсит специальные команды из ответа AI и возвращает
    (очищенный текст, список доп. сообщений)
    """
    extras = []
    clean  = text

    # [TASK: минуты | описание]
    task_match = re.search(r'\[TASK:\s*(\d+)\s*\|\s*(.+?)\]', text)
    if task_match:
        mins, desc = int(task_match.group(1)), task_match.group(2).strip()
        add_task(user_id, desc, mins)
        clean = clean.replace(task_match.group(0), "").strip()

    # [DAILY_TASK: время | описание] — ежедневная задача (утро/обед/вечер)
    daily_match = re.search(r'\[DAILY_TASK:\s*([0-9:]+)\s*\|\s*(.+?)\]', text)
    if daily_match:
        time_str, desc = daily_match.group(1).strip(), daily_match.group(2).strip()
        add_daily_task(user_id, desc, time_str)
        clean = clean.replace(daily_match.group(0), "").strip()

    # [REMOVE_DAILY_TASK: текст] — удалить ежедневную задачу
    remove_daily_match = re.search(r'\[REMOVE_DAILY_TASK:\s*(.+?)\]', text)
    if remove_daily_match:
        desc = remove_daily_match.group(1).strip()
        remove_daily_task(user_id, desc)
        clean = clean.replace(remove_daily_match.group(0), "").strip()

    # [SHOW_TASKS]
    if "[SHOW_TASKS]" in text:
        tasks       = [t for t in load_tasks() if t["user_id"] == user_id and not t.get("repeat") and not t["done"]]
        daily_tasks = get_daily_tasks(user_id)
        lines = []
        if daily_tasks:
            lines.append("📋 ежедневные задачи:")
            for t in sorted(daily_tasks, key=lambda x: x["time"]):
                lines.append(f"  • {t['time']} — {t['text']}")
        if tasks:
            if lines:
                lines.append("")
            lines.append("📋 разовые напоминания:")
            for t in tasks:
                dt = datetime.fromisoformat(t["remind_at"])
                lines.append(f"  • {t['text']} — в {dt.strftime('%H:%M')}")
        if lines:
            extras.append(("text", "\n".join(lines)))
        else:
            extras.append(("text", "задач нет"))
        clean = clean.replace("[SHOW_TASKS]", "").strip()

    # [CLEAR_TASKS]
    if "[CLEAR_TASKS]" in text:
        clear_user_tasks(user_id)
        extras.append(("text", "задачи очищены ✅"))
        clean = clean.replace("[CLEAR_TASKS]", "").strip()

    # [WEATHER: город]
    w_match = re.search(r'\[WEATHER:\s*(.+?)\]', text)
    if w_match:
        result = get_weather(w_match.group(1).strip())
        extras.append(("text", result))
        clean = clean.replace(w_match.group(0), "").strip()

    # [RATE: валюта]
    r_match = re.search(r'\[RATE:\s*(.+?)\]', text)
    if r_match:
        result = get_exchange_rate(r_match.group(1).strip())
        extras.append(("text", result))
        clean = clean.replace(r_match.group(0), "").strip()

    # [CONVERT: сумма FROM TO]
    c_match = re.search(r'\[CONVERT:\s*(\d+)\s+(\w+)\s+(\w+)\]', text)
    if c_match:
        result = convert_currency(float(c_match.group(1)), c_match.group(2), c_match.group(3))
        extras.append(("text", result))
        clean = clean.replace(c_match.group(0), "").strip()

    # [WIKI: запрос]
    wiki_match = re.search(r'\[WIKI:\s*(.+?)\]', text)
    if wiki_match:
        result = search_wikipedia(wiki_match.group(1).strip())
        if result:
            extras.append(("text", result))
        clean = clean.replace(wiki_match.group(0), "").strip()

    # [NEWS: тема]
    news_match = re.search(r'\[NEWS:\s*(.+?)\]', text)
    if news_match:
        news = get_news(news_match.group(1).strip())
        if news:
            extras.append(("text", "📰 " + "\n📰 ".join(news)))
        clean = clean.replace(news_match.group(0), "").strip()

    # [FACT]
    if "[FACT]" in text:
        import random
        from config import FACTS
        extras.append(("text", random.choice(FACTS)))
        clean = clean.replace("[FACT]", "").strip()

    # [QUOTE]
    if "[QUOTE]" in text:
        import random
        from config import QUOTES
        extras.append(("text", random.choice(QUOTES)))
        clean = clean.replace("[QUOTE]", "").strip()

    return clean.strip(), extras
