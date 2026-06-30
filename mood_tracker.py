"""
mood_tracker.py — настроение меняется от поведения пользователя.
Если грубит несколько раз → обида → холодные ответы пока не извинится.
"""

import json, os, re
from datetime import datetime
from config import TZ

MOOD_FILE = "kamilla_mood.json"

# ── Ключевые слова ────────────────────────────────────────────────────────────

RUDE_KEYWORDS = [
    "заткнись", "тупая", "идиотка", "дура", "бесишь", "надоела",
    "отстань", "ненавижу тебя", "ты плохая", "молчи", "заткнись",
    "дебил", "тупой бот", "глупая", "раздражаешь", "ты отстой",
    "иди нахуй", "иди нафиг", "пошла нахуй", "пошла нафиг",
    "shut up", "stupid", "idiot", "hate you",
]

APOLOGY_KEYWORDS = [
    "прости", "извини", "извиняюсь", "прошу прощения", "сорри",
    "sorry", "my bad", "я был неправ", "я не хотел",
    "не обижайся", "я виноват",
]

# ── Состояния настроения ──────────────────────────────────────────────────────

MOOD_STATES = {
    "normal":   "обычное",
    "offended": "обиженное",    # лёгкая обида
    "cold":     "холодное",     # серьёзная обида
    "warm":     "тёплое",       # после примирения
}

# ── Загрузка / сохранение ─────────────────────────────────────────────────────

def _load() -> dict:
    if os.path.exists(MOOD_FILE):
        with open(MOOD_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save(data: dict):
    with open(MOOD_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _get_user(user_id: int) -> dict:
    data = _load()
    return data.get(str(user_id), {
        "mood":        "normal",
        "rude_count":  0,
        "last_rude":   None,
        "offended_at": None,
    })

def _set_user(user_id: int, state: dict):
    data            = _load()
    data[str(user_id)] = state
    _save(data)

# ── Основная логика ───────────────────────────────────────────────────────────

def process_message(user_id: int, text: str) -> str | None:
    """
    Анализирует сообщение.
    Возвращает строку-инструкцию для system prompt если настроение изменилось,
    иначе None.
    """
    state     = _get_user(user_id)
    text_low  = text.lower()

    # Проверяем извинение
    is_apology = any(kw in text_low for kw in APOLOGY_KEYWORDS)
    if is_apology and state["mood"] in ("offended", "cold"):
        state["mood"]       = "warm"
        state["rude_count"] = 0
        _set_user(user_id, state)
        return "warm_after_apology"

    # Проверяем грубость
    is_rude = any(kw in text_low for kw in RUDE_KEYWORDS)
    if is_rude:
        state["rude_count"] = state.get("rude_count", 0) + 1
        state["last_rude"]  = datetime.now(TZ).isoformat()

        if state["rude_count"] >= 3:
            state["mood"]       = "cold"
            state["offended_at"] = datetime.now(TZ).isoformat()
        elif state["rude_count"] >= 1:
            state["mood"]       = "offended"
            state["offended_at"] = datetime.now(TZ).isoformat()

        _set_user(user_id, state)
        return f"rude_{state['mood']}"

    # Постепенно возвращаемся к нормальному если давно не грубил
    if state["mood"] == "warm":
        state["mood"] = "normal"
        _set_user(user_id, state)

    return None

def get_mood_context(user_id: int) -> str:
    """Возвращает инструкцию для system prompt на основе текущего настроения"""
    state = _get_user(user_id)
    mood  = state.get("mood", "normal")

    contexts = {
        "normal": "",

        "offended": (
            "\n\nНАСТРОЕНИЕ: немного обиделась на грубость. "
            "Отвечай чуть холоднее обычного — короче, суше, без тепла. "
            "Не объясняй почему. Просто чуть дистанция. "
            "Если извинится — сразу оттаивай."
        ),

        "cold": (
            "\n\nНАСТРОЕНИЕ: серьёзно обиделась. "
            "Отвечай очень коротко и холодно — 'ок', 'понятно', 'как скажешь'. "
            "Никакого тепла, никаких эмодзи. Ждёшь извинений. "
            "Пока не извинится — держи дистанцию."
        ),

        "warm": (
            "\n\nНАСТРОЕНИЕ: только что помирились после обиды. "
            "Оттаиваешь — стала теплее чем обычно. "
            "Можно сказать 'ладно, проехали' или просто стать мягче. "
            "Не затягивай тему обиды."
        ),
    }

    return contexts.get(mood, "")

def get_mood_reaction(event: str) -> str | None:
    """Возвращает готовую фразу реакции на событие"""
    import random
    reactions = {
        "rude_offended": [
            "ок",
            "понятно",
            "ясно",
            "хорошо",
        ],
        "rude_cold": [
            "как скажешь",
            "ок",
            "понятно",
            ".",
        ],
        "warm_after_apology": [
            "ладно. проехали",
            "ок. забыли",
            "хорошо. проехали",
            "принято",
        ],
    }
    options = reactions.get(event, [])
    return random.choice(options) if options else None

def get_current_mood(user_id: int) -> str:
    return _get_user(user_id).get("mood", "normal")