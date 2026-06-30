"""
humanizer.py — делает общение живым:
- разбивает ответ на несколько сообщений
- добавляет самоисправления
- имитирует паузы и печать
- иногда добавляет "кстати...", "подожди", "нет я не так сказала"
"""

import asyncio, random, re
from datetime import datetime
from config import TZ

# ── Вероятности поведения ─────────────────────────────────────────────────────

PROB_SPLIT         = 0.55
PROB_SELF_CORRECT  = 0.18
PROB_KСТАТИ        = 0.20
PROB_TRAILING      = 0.12

# ── Фразы самоисправления ─────────────────────────────────────────────────────

SELF_CORRECTIONS = [
    "то есть я хотела сказать",
    "нет подожди",
    "точнее",
    "вернее",
    "ну то есть",
    "хм. нет. не так",
    "стоп, я не то имела в виду",
    "переформулирую",
]

KСТАТИ_PHRASES = [
    "кстати",
    "а ещё",
    "и да",
    "о, и вот ещё",
    "ладно и ещё одно",
    "да, и",
]

TRAILING_PHRASES = [
    "вот",
    "в общем",
    "ну ты понял",
    "короче",
    "как-то так",
    "не знаю зачем это сказала",
    "просто мысль",
    "всё",
]

# ── Утилиты ───────────────────────────────────────────────────────────────────

def _typing_pause(text: str) -> float:
    words = len(text.split())
    base  = words * random.uniform(0.3, 0.6)
    return min(max(base, 1.0), 6.0)

def _between_pause() -> float:
    return random.uniform(1.2, 3.5)

def _split_naturally(text: str) -> list[str]:
    text  = text.strip()
    words = text.split()

    if len(words) <= 6:
        return [text]

    if len(words) <= 15:
        if random.random() > 0.5:
            return [text]
        mid = len(words) // 2
        for i in range(mid, min(mid + 3, len(words))):
            if words[i].endswith(('.', '!', '?', '...', ',')):
                part1 = " ".join(words[:i+1]).rstrip(',')
                part2 = " ".join(words[i+1:])
                if part2:
                    return [part1, part2]
        return [text]

    parts     = []
    sentences = re.split(r'(?<=[.!?…])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) == 1:
        mid  = len(words) // 2
        cut  = random.randint(mid - 2, mid + 2)
        cut  = max(3, min(cut, len(words) - 3))
        parts = [
            " ".join(words[:cut]),
            " ".join(words[cut:])
        ]
    elif len(sentences) == 2:
        parts = sentences
    else:
        cut = random.randint(1, len(sentences) - 1)
        parts = [
            " ".join(sentences[:cut]),
            " ".join(sentences[cut:])
        ]
        if cut + 1 <= len(sentences) - 1:
            cut2 = random.randint(cut + 1, len(sentences) - 1)
        else:
            cut2 = len(sentences) - 1
            parts = [
                " ".join(sentences[:cut]),
                " ".join(sentences[cut:cut2]),
                " ".join(sentences[cut2:])
            ]

    return [p for p in parts if p.strip()]

def _maybe_add_self_correction(parts: list[str]) -> list[str]:
    if len(parts) < 2 or random.random() > PROB_SELF_CORRECT:
        return parts

    correction = random.choice(SELF_CORRECTIONS)
    second     = parts[1]

    # ИСПРАВЛЕНО: first_word вычислялся но не использовался — убран
    corrected = f"{correction}... {second[0].lower() + second[1:] if len(second) > 1 else second}"

    return [parts[0], corrected] + parts[2:]

def _maybe_add_kстати(parts: list[str], original_text: str) -> list[str]:
    if random.random() > PROB_KСТАТИ:
        return parts

    kстати = random.choice(KСТАТИ_PHRASES)

    additions = [
        f"{kстати}. ты сам как к этому относишься?",
        f"{kстати}. мне интересно что ты думаешь",
        f"{kстати}. давно хотела спросить",
        f"{kстати}. не важно",
        f"{kстати}. ладно потом",
        f"{kстати}. забудь",
        f"{kстати}. нет ничего",
    ]

    return parts + [random.choice(additions)]

def _maybe_add_trailing(parts: list[str]) -> list[str]:
    if random.random() > PROB_TRAILING:
        return parts
    return parts + [random.choice(TRAILING_PHRASES)]

# ── Главная функция ───────────────────────────────────────────────────────────

async def humanize_and_send(send_func, chat_id: int, text: str,
                             reply_to=None, user_message: str = ""):
    if not text or not text.strip():
        return

    if random.random() < PROB_SPLIT and len(text.split()) > 5:
        parts = _split_naturally(text)
    else:
        parts = [text]

    if len(parts) > 1:
        parts = _maybe_add_self_correction(parts)

    if len(parts) <= 2:
        parts = _maybe_add_kстати(parts, text)

    if len(parts) == 1:
        parts = _maybe_add_trailing(parts)

    parts = [p.strip() for p in parts if p.strip()]

    for i, part in enumerate(parts):
        is_first = (i == 0)

        pause = _typing_pause(part)
        await asyncio.sleep(pause)

        if is_first and reply_to:
            await send_func(chat_id, part, reply_to=reply_to, user_message=user_message)
        else:
            await send_func(chat_id, part, user_message=user_message)

        if i < len(parts) - 1:
            await asyncio.sleep(_between_pause())

# ── Ночной режим ──────────────────────────────────────────────────────────────

def get_time_factor() -> float:
    hour = datetime.now(TZ).hour
    if 23 <= hour or hour < 7:
        return 1.5
    elif 7 <= hour < 9:
        return 1.1
    return 1.0
