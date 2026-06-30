"""
humanizer.py — делает общение живым:
- разбивает ответ на несколько сообщений
- имитирует паузы и печать
"""

import asyncio, random, re
from datetime import datetime
from config import TZ

# ── Вероятности поведения ─────────────────────────────────────────────────────

PROB_SPLIT = 0.55

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

# ── Главная функция ───────────────────────────────────────────────────────────

async def humanize_and_send(send_func, chat_id: int, text: str,
                             reply_to=None, user_message: str = ""):
    if not text or not text.strip():
        return

    if random.random() < PROB_SPLIT and len(text.split()) > 5:
        parts = _split_naturally(text)
    else:
        parts = [text]

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
