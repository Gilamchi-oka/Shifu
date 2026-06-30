"""
activity_tracker.py — отслеживает когда пользователь активен
и подстраивает проактивные сообщения под его реальный режим дня
"""

import json, os
from datetime import datetime, timedelta
from collections import defaultdict
from config import TZ

# ИСПРАВЛЕНО: ACTIVITY_FILE вынесен на уровень модуля — теперь memory.py может его импортировать
ACTIVITY_FILE = "kamilla_activity.json"

# ── Загрузка / сохранение ─────────────────────────────────────────────────────

def _load() -> dict:
    if os.path.exists(ACTIVITY_FILE):
        with open(ACTIVITY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save(data: dict):
    with open(ACTIVITY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Запись активности ─────────────────────────────────────────────────────────

def record_activity(user_id: int):
    """Вызывается каждый раз когда пользователь пишет"""
    data    = _load()
    key     = str(user_id)
    now     = datetime.now(TZ)
    hour    = now.hour
    weekday = now.weekday()  # 0=пн, 6=вс

    if key not in data:
        data[key] = {
            "hours":    [0] * 24,
            "weekdays": [0] * 7,
            "total":    0,
            "last_active": None,
            "streak_days": 0,
            "first_seen": now.isoformat(),
        }

    data[key]["hours"][hour]       += 1
    data[key]["weekdays"][weekday] += 1
    data[key]["total"]             += 1
    data[key]["last_active"]        = now.isoformat()

    _save(data)

# ── Анализ активности ─────────────────────────────────────────────────────────

def get_active_hours(user_id: int) -> list[int]:
    """Возвращает топ-3 часа когда пользователь чаще всего пишет"""
    data = _load()
    key  = str(user_id)
    if key not in data or data[key]["total"] < 10:
        return [19, 20, 21]

    hours = data[key]["hours"]
    top   = sorted(range(24), key=lambda h: hours[h], reverse=True)[:3]
    return sorted(top)

def get_best_proactive_hour(user_id: int) -> int | None:
    """Возвращает лучший час для проактивного сообщения."""
    data = _load()
    key  = str(user_id)
    if key not in data or data[key]["total"] < 10:
        return None

    hours = data[key]["hours"]
    now   = datetime.now(TZ).hour

    candidates = [
        (h, hours[h]) for h in range(8, 23)
        if hours[h] > 0
    ]
    if not candidates:
        return None

    future = [(h, c) for h, c in candidates if h > now]
    if future:
        return max(future, key=lambda x: x[1])[0]

    return None

def is_user_likely_active(user_id: int) -> bool:
    """Проверяет — вероятно ли что пользователь сейчас активен."""
    data = _load()
    key  = str(user_id)
    if key not in data or data[key]["total"] < 5:
        hour = datetime.now(TZ).hour
        return 9 <= hour <= 23

    hours   = data[key]["hours"]
    weekday = datetime.now(TZ).weekday()
    hour    = datetime.now(TZ).hour

    avg_hour  = sum(hours) / 24
    this_hour = hours[hour]

    weekdays    = data[key]["weekdays"]
    avg_weekday = sum(weekdays) / 7
    this_day    = weekdays[weekday]

    hour_active = this_hour >= avg_hour * 0.7
    day_active  = this_day  >= avg_weekday * 0.7

    return hour_active and day_active

def get_activity_summary(user_id: int) -> str:
    """Текстовое описание активности для дебага/логов"""
    data = _load()
    key  = str(user_id)
    if key not in data:
        return "нет данных"

    d              = data[key]
    hours          = get_active_hours(user_id)
    total          = d.get("total", 0)
    weekdays_names = ["пн","вт","ср","чт","пт","сб","вс"]
    top_day        = weekdays_names[d["weekdays"].index(max(d["weekdays"]))]

    return (
        f"Всего сообщений: {total} | "
        f"Активные часы: {', '.join(f'{h}:00' for h in hours)} | "
        f"Самый активный день: {top_day}"
    )

def get_mood_by_weekday() -> str:
    """Настроение дня недели для personality."""
    weekday = datetime.now(TZ).weekday()
    moods = {
        0: "понедельник — чуть серьёзнее обычного, втягивается в неделю",
        1: "вторник — рабочий настрой, сдержанная",
        2: "среда — середина недели, немного устала но держится",
        3: "четверг — чувствует что конец недели близко, чуть теплее",
        4: "пятница — игривая, расслабленная, пятница же",
        5: "суббота — свободная, может болтать сколько угодно",
        6: "воскресенье — задумчивая, немного меланхоличная, не хочет чтоб заканчивалось",
    }
    return moods.get(weekday, "")