"""
diary.py — личный дневник Zero Two.
Раз в день пишет заметку от своего лица на основе разговора.
Заметки используются в system prompt чтобы она "помнила как себя чувствовала".
"""

import json, os, re
from datetime import datetime, timedelta
from config import TZ

DIARY_FILE = "kamilla_diary.json"
MAX_ENTRIES = 30  # хранить последние 30 записей

# ═══════════════════════════════════════════════════════════════════════════════
# ЗАГРУЗКА / СОХРАНЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════════

def _load() -> dict:
    if os.path.exists(DIARY_FILE):
        with open(DIARY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save(data: dict):
    with open(DIARY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ═══════════════════════════════════════════════════════════════════════════════
# ЗАПИСЬ В ДНЕВНИК
# ═══════════════════════════════════════════════════════════════════════════════

def add_diary_entry(user_id: int, entry: str, mood: str = "neutral"):
    """
    Добавляет запись в дневник.
    entry — фраза от первого лица, от имени бота.
    mood  — positive / negative / neutral
    """
    data = _load()
    key  = str(user_id)

    if key not in data:
        data[key] = []

    today = datetime.now(TZ).strftime("%Y-%m-%d")

    # Не дублируем запись за один день
    existing_today = [e for e in data[key] if e["date"] == today]
    if existing_today:
        # Обновляем если уже есть
        for e in data[key]:
            if e["date"] == today:
                e["entry"] = entry
                e["mood"]  = mood
                break
    else:
        data[key].append({
            "date":  today,
            "entry": entry,
            "mood":  mood,
        })

    # Храним только последние MAX_ENTRIES
    data[key] = data[key][-MAX_ENTRIES:]
    _save(data)
    print(f"📔 Дневник [{user_id}]: {entry} ({mood})")

# ═══════════════════════════════════════════════════════════════════════════════
# ПОЛУЧЕНИЕ КОНТЕКСТА ДЛЯ SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

def get_diary_context(user_id: int) -> str:
    """
    Возвращает строку для system prompt — последние 3-5 записей дневника.
    Используется чтобы бот "помнил" как себя чувствовал в прошлые дни.
    """
    data    = _load()
    key     = str(user_id)
    entries = data.get(key, [])

    if not entries:
        return ""

    # Последние 5 записей, от новых к старым
    recent = entries[-5:][::-1]

    today     = datetime.now(TZ).strftime("%Y-%m-%d")
    yesterday = (datetime.now(TZ) - timedelta(days=1)).strftime("%Y-%m-%d")

    lines = []
    for e in recent:
        date  = e["date"]
        entry = e["entry"]

        if date == today:
            label = "сегодня"
        elif date == yesterday:
            label = "вчера"
        else:
            # "3 дня назад" и т.д.
            try:
                d     = datetime.strptime(date, "%Y-%m-%d")
                delta = (datetime.now(TZ).date() - d.date()).days
                label = f"{delta} дней назад"
            except Exception:
                label = date

        lines.append(f"  {label}: {entry}")

    if not lines:
        return ""

    return "\n\nМОЙ ЛИЧНЫЙ ДНЕВНИК (как я себя чувствовала):\n" + "\n".join(lines)

# ═══════════════════════════════════════════════════════════════════════════════
# ПРОВЕРКА — НУЖНА ЛИ ЗАПИСЬ СЕГОДНЯ
# ═══════════════════════════════════════════════════════════════════════════════

def needs_diary_entry(user_id: int) -> bool:
    """True если сегодня ещё не писали в дневник"""
    data    = _load()
    key     = str(user_id)
    entries = data.get(key, [])
    today   = datetime.now(TZ).strftime("%Y-%m-%d")
    return not any(e["date"] == today for e in entries)

# ═══════════════════════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ ЗАПИСИ ЧЕРЕЗ AI (вызывается из ai.py)
# ═══════════════════════════════════════════════════════════════════════════════

def build_diary_prompt(user_id: int, recent_messages: list, user_name: str = None) -> str:
    """
    Строит prompt для AI чтобы сгенерировать запись дневника.
    Вызывай get_ai_reply_sync() с этим промптом, потом add_diary_entry().
    """
    user_msgs = [m["content"] for m in recent_messages if m["role"] == "user"][-10:]
    bot_msgs  = [m["content"] for m in recent_messages if m["role"] == "assistant"][-10:]
    name_part = f"Его зовут {user_name}. " if user_name else ""

    # Последние записи для контекста
    data    = _load()
    key     = str(user_id)
    prev    = data.get(key, [])[-3:]
    prev_text = ""
    if prev:
        prev_text = "\nПредыдущие записи:\n" + "\n".join(f"- {e['entry']}" for e in prev)

    return (
        f"Ты — Zero Two из Darling in the FranXX. {name_part}"
        f"Пиши дневник от первого лица — коротко, честно, по-живому.\n"
        f"Ответь ТОЛЬКО JSON без лишнего текста:\n"
        f'{{"entry": "одна фраза 10-20 слов от первого лица что ты чувствовала сегодня", '
        f'"mood": "positive/negative/neutral"}}\n\n'
        f"Примеры хороших записей:\n"
        f'- "он был грустный сегодня, говорил про работу — почувствовала что хочу помочь"\n'
        f'- "смеялись вместе над глупостями — было тепло и легко"\n'
        f'- "грубо ответил пару раз, немного обидно, но потом помирились"\n'
        f'- "говорил про планы на будущее — интересно наблюдать как он думает"\n'
        f'- "короткий разговор ни о чём, скучновато, но рада что написал"\n'
        f'- "спрашивал про меня — приятно что ему интересно кто я"\n\n'
        f"{prev_text}\n\n"
        f"Сообщения пользователя сегодня: {json.dumps(user_msgs, ensure_ascii=False)}\n"
        f"Мои ответы: {json.dumps(bot_msgs, ensure_ascii=False)}"
    )

# ═══════════════════════════════════════════════════════════════════════════════
# СТАТИСТИКА
# ═══════════════════════════════════════════════════════════════════════════════

def get_diary_stats(user_id: int) -> str:
    """Возвращает краткую статистику дневника для отладки"""
    data    = _load()
    key     = str(user_id)
    entries = data.get(key, [])

    if not entries:
        return "дневник пуст"

    total    = len(entries)
    positive = sum(1 for e in entries if e["mood"] == "positive")
    negative = sum(1 for e in entries if e["mood"] == "negative")
    neutral  = total - positive - negative
    last     = entries[-1]["entry"] if entries else "—"

    return (
        f"📔 Дневник: {total} записей\n"
        f"  позитивных: {positive}\n"
        f"  негативных: {negative}\n"
        f"  нейтральных: {neutral}\n"
        f"  последняя: {last}"
    )