"""
mood_predictor.py — предсказывает настроение пользователя
по паттернам: день недели + час → какое настроение обычно бывает.
Через 7 дней наблюдений начинает подстраиваться заранее.
"""

import json, os
from datetime import datetime
from config import TZ

PREDICTOR_FILE = "kamilla_mood_patterns.json"

# ═══════════════════════════════════════════════════════════════════════════════
# СТРУКТУРА ДАННЫХ
# ═══════════════════════════════════════════════════════════════════════════════
#
# {
#   "user_id": {
#     "patterns": {
#       "0_9":  {"positive": 2, "negative": 5, "neutral": 1},  # пн, 9 утра
#       "0_18": {"positive": 7, "negative": 1, "neutral": 2},  # пн, 18 вечера
#       ...
#     },
#     "total_days": 3,       # сколько дней наблюдаем
#     "last_record": "2024-01-15"
#   }
# }
#
# Ключ паттерна: "{weekday}_{hour_block}"
# weekday: 0=пн ... 6=вс
# hour_block: 0-5 (ночь), 6-8 (утро), 9-12 (день), 13-17 (обед/день),
#             18-21 (вечер), 22-23 (поздно)

# ═══════════════════════════════════════════════════════════════════════════════
# ЗАГРУЗКА / СОХРАНЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════════

def _load() -> dict:
    if os.path.exists(PREDICTOR_FILE):
        with open(PREDICTOR_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save(data: dict):
    with open(PREDICTOR_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _get_user(user_id: int) -> dict:
    data = _load()
    return data.get(str(user_id), {
        "patterns":   {},
        "total_days": 0,
        "last_record": None,
    })

def _set_user(user_id: int, state: dict):
    data = _load()
    data[str(user_id)] = state
    _save(data)

# ═══════════════════════════════════════════════════════════════════════════════
# КЛЮЧ ПАТТЕРНА
# ═══════════════════════════════════════════════════════════════════════════════

def _make_key(weekday: int, hour: int) -> str:
    return f"{weekday}_{hour}"

def _get_now_key() -> str:
    now = datetime.now(TZ)
    return _make_key(now.weekday(), now.hour)

# ═══════════════════════════════════════════════════════════════════════════════
# ЗАПИСЬ ПАТТЕРНА
# ═══════════════════════════════════════════════════════════════════════════════

def record_mood_pattern(user_id: int, mood: str):
    """
    Записывает текущее настроение пользователя в паттерн.
    mood: "positive" | "negative" | "neutral"
    Вызывать когда известно реальное настроение (из emotion detection).
    """
    if mood not in ("positive", "negative", "neutral"):
        return

    now   = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")
    key   = _get_now_key()
    state = _get_user(user_id)

    # Считаем дни наблюдений
    if state.get("last_record") != today:
        state["total_days"] = state.get("total_days", 0) + 1
        state["last_record"] = today

    patterns = state.get("patterns", {})
    if key not in patterns:
        patterns[key] = {"positive": 0, "negative": 0, "neutral": 0}

    patterns[key][mood] = patterns[key].get(mood, 0) + 1
    state["patterns"] = patterns
    _set_user(user_id, state)

# ═══════════════════════════════════════════════════════════════════════════════
# ПРЕДСКАЗАНИЕ
# ═══════════════════════════════════════════════════════════════════════════════

def predict_mood(user_id: int) -> str | None:
    """
    Предсказывает настроение на текущий момент.
    Возвращает "positive" / "negative" / "neutral" / None если данных мало.
    Начинает предсказывать после 5 дней наблюдений.
    """
    state = _get_user(user_id)

    if state.get("total_days", 0) < 5:
        return None  # мало данных

    key      = _get_now_key()
    patterns = state.get("patterns", {})

    if key not in patterns:
        # Нет данных для этого слота — смотрим соседние часы
        now      = datetime.now(TZ)
        weekday  = now.weekday()
        hour     = now.hour

        neighbors = []
        for h in [hour - 1, hour + 1]:
            if 0 <= h <= 23:
                nk = _make_key(weekday, h)
                if nk in patterns:
                    neighbors.append(patterns[nk])

        if not neighbors:
            return None

        # Усредняем соседей
        total = {"positive": 0, "negative": 0, "neutral": 0}
        for n in neighbors:
            for m in total:
                total[m] += n.get(m, 0)
        slot = total
    else:
        slot = patterns[key]

    total_count = sum(slot.values())
    if total_count < 3:
        return None  # мало наблюдений для этого слота

    # Берём доминирующее настроение
    dominant = max(slot, key=lambda m: slot[m])
    dominant_pct = slot[dominant] / total_count

    # Предсказываем только если паттерн выражен (>50%)
    if dominant_pct < 0.5:
        return None

    return dominant

# ═══════════════════════════════════════════════════════════════════════════════
# КОНТЕКСТ ДЛЯ SYSTEM PROMPT
# ═══════════════════════════════════════════════════════════════════════════════

WEEKDAYS_RU = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]

def _hour_label(hour: int) -> str:
    if 0 <= hour <= 5:   return "ночью"
    if 6 <= hour <= 8:   return "утром"
    if 9 <= hour <= 12:  return "днём"
    if 13 <= hour <= 17: return "после обеда"
    if 18 <= hour <= 21: return "вечером"
    return "поздно вечером"

def get_prediction_context(user_id: int) -> str:
    """
    Возвращает строку для system prompt с предсказанием настроения.
    """
    predicted = predict_mood(user_id)
    if not predicted:
        return ""

    now      = datetime.now(TZ)
    weekday  = WEEKDAYS_RU[now.weekday()]
    hour_lbl = _hour_label(now.hour)

    mood_hints = {
        "negative": (
            f"\n\nПРЕДСКАЗАНИЕ: по паттернам, {weekday} {hour_lbl} у него обычно "
            f"плохое/тяжёлое настроение. Будь чуть мягче и внимательнее. "
            f"Не лезь с советами — просто будь рядом. "
            f"Если жалуется — не удивляйся, для него это типично в это время."
        ),
        "positive": (
            f"\n\nПРЕДСКАЗАНИЕ: по паттернам, {weekday} {hour_lbl} у него обычно "
            f"хорошее настроение. Можно быть чуть игривее и энергичнее. "
            f"Он скорее всего открыт к общению."
        ),
        "neutral": "",
    }

    return mood_hints.get(predicted, "")

# ═══════════════════════════════════════════════════════════════════════════════
# АВТОЗАПИСЬ ИЗ EMOTION DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

# Маппинг эмоций из personality.py → positive/negative/neutral
EMOTION_TO_MOOD = {
    "joy":        "positive",
    "excitement": "positive",
    "love":       "positive",
    "gratitude":  "positive",
    "sadness":    "negative",
    "anger":      "negative",
    "grief":      "negative",
    "loneliness": "negative",
    "anxiety":    "negative",
    "fear":       "negative",
    "neutral":    "neutral",
    "tired":      "negative",
    "bored":      "negative",
}

def record_from_emotion(user_id: int, emotion: str | None):
    """
    Удобная обёртка — принимает эмоцию из detect_emotion()
    и записывает в паттерн.
    """
    if not emotion:
        return
    mood = EMOTION_TO_MOOD.get(emotion, "neutral")
    record_mood_pattern(user_id, mood)

# ═══════════════════════════════════════════════════════════════════════════════
# СТАТИСТИКА / ОТЛАДКА
# ═══════════════════════════════════════════════════════════════════════════════

def get_predictor_stats(user_id: int) -> str:
    state    = _get_user(user_id)
    total    = state.get("total_days", 0)
    patterns = state.get("patterns", {})

    if not patterns:
        return "паттернов ещё нет — нужно больше данных"

    # Самые "тяжёлые" слоты
    heavy = []
    for key, counts in patterns.items():
        neg = counts.get("negative", 0)
        tot = sum(counts.values())
        if tot >= 3 and neg / tot >= 0.5:
            wd, hr = key.split("_")
            heavy.append(f"{WEEKDAYS_RU[int(wd)]} {_hour_label(int(hr))} — чаще плохое")

    lines = [f"📊 Паттерны настроения ({total} дней наблюдений):"]
    if heavy:
        lines.append("  Тяжёлые слоты:")
        for h in heavy[:5]:
            lines.append(f"    • {h}")
    else:
        lines.append("  выраженных паттернов пока нет")

    predicted = predict_mood(user_id)
    if predicted:
        lines.append(f"  Сейчас предсказано: {predicted}")

    return "\n".join(lines)