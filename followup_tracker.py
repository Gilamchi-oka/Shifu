"""
followup_tracker.py — запоминает детали типа "иду на встречу"
и через нужное время сама спрашивает как всё прошло
"""

import json, os, re
from datetime import datetime, timedelta
from config import TZ

FOLLOWUP_FILE = "kamilla_followups.json"

# ── Паттерны для отслеживания ─────────────────────────────────────────────────

# (regex, часы до follow-up, шаблон вопроса)
FOLLOWUP_PATTERNS = [
    (r'иду на встречу|иду на собеседование',  3,  "ну как встреча прошла?"),
    (r'иду на свидание',                       4,  "ну как свидание? рассказывай"),
    (r'иду в (спортзал|зал|тренировка)',        2,  "как потренировался?"),
    (r'ложусь спать|иду спать|спокойной',      8,  "выспался?"),
    (r'иду на работу|еду на работу',            9,  "как день прошёл?"),
    (r'еду в больниц|иду к врачу',             3,  "ну как врач? всё нормально?"),
    (r'сдаю экзамен|иду на экзамен',           4,  "ну как экзамен сдал?"),
    (r'лечу|еду в аэропорт|улетаю',           24,  "долетел нормально?"),
    (r'иду на вечеринку|иду на тусовку',        6,  "ну как погулял? весело было?"),
    (r'иду на концерт|иду в кино|иду в театр',  4,  "ну как? понравилось?"),
    (r'начинаю (проект|работу над)',           48,  "кстати, как там с проектом?"),
    (r'попробую|попробую сегодня',             24,  "кстати, попробовал? как получилось?"),
    (r'поговорю с|поговорю сегодня с',         12,  "поговорил в итоге?"),
]

# ── Загрузка / сохранение ─────────────────────────────────────────────────────

def _load() -> dict:
    if os.path.exists(FOLLOWUP_FILE):
        with open(FOLLOWUP_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save(data: dict):
    with open(FOLLOWUP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Основная логика ───────────────────────────────────────────────────────────

def check_and_add_followup(user_id: int, text: str) -> bool:
    """
    Проверяет текст на паттерны. Если нашёл — добавляет follow-up.
    Возвращает True если что-то добавил.
    """
    text_low = text.lower()
    data     = _load()
    key      = str(user_id)

    if key not in data:
        data[key] = []

    for pattern, hours, question in FOLLOWUP_PATTERNS:
        if re.search(pattern, text_low):
            ask_at = datetime.now(TZ) + timedelta(hours=hours)

            # Не добавляем дубликат того же вопроса
            existing = [f for f in data[key] if not f["done"] and f["question"] == question]
            if existing:
                continue

            data[key].append({
                "question":     question,
                "ask_at":       ask_at.isoformat(),
                "trigger_text": text[:60],
                "done":         False,
            })
            _save(data)
            print(f"📌 Follow-up добавлен для {user_id}: '{question}' через {hours}ч")
            return True

    return False

def get_pending_followups(user_id: int) -> list[str]:
    """
    Возвращает список вопросов которые уже пора задать.
    Помечает их как done.
    """
    data = _load()
    key  = str(user_id)
    now  = datetime.now(TZ)

    if key not in data:
        return []

    pending = []
    for item in data[key]:
        if item["done"]:
            continue
        ask_at = datetime.fromisoformat(item["ask_at"])
        if ask_at.tzinfo is None:
            from pytz import UTC
            ask_at = UTC.localize(ask_at)
        if now >= ask_at:
            pending.append(item["question"])
            item["done"] = True

    if pending:
        _save(data)

    return pending

def has_pending_followups(user_id: int) -> bool:
    """Быстрая проверка — есть ли что спросить"""
    data = _load()
    key  = str(user_id)
    now  = datetime.now(TZ)

    for item in data.get(key, []):
        if item["done"]:
            continue
        ask_at = datetime.fromisoformat(item["ask_at"])
        if ask_at.tzinfo is None:
            from pytz import UTC
            ask_at = UTC.localize(ask_at)
        if now >= ask_at:
            return True

    return False

def clear_old_followups(user_id: int):
    """Чистит выполненные follow-up старше 7 дней"""
    data     = _load()
    key      = str(user_id)
    week_ago = datetime.now(TZ) - timedelta(days=7)

    if key not in data:
        return

    data[key] = [
        f for f in data[key]
        if not f["done"] or
        datetime.fromisoformat(f["ask_at"]) > week_ago
    ]
    _save(data)