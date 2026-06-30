"""
news_reaction.py — живая реакция на новости с мнением от лица Zero Two.
Если пользователь упоминает что-то из новостей — бот в курсе и имеет мнение.
"""

import json, re, random
import requests
from config import TZ
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════════════════
# ТРИГГЕРЫ — когда искать новости
# ═══════════════════════════════════════════════════════════════════════════════

# Фразы которые сигнализируют что пользователь говорит о новостях/событиях
NEWS_TRIGGERS = [
    "слышал", "слышала", "видел", "видела", "читал", "читала",
    "говорят", "пишут", "новость", "новости", "случилось",
    "произошло", "оказывается", "оказалось", "говорят что",
    "типа", "короче", "вот это да", "ты знаешь что",
    "ты в курсе", "ты слышала", "а ты знаешь",
    "что думаешь о", "как тебе", "твоё мнение",
]

# Темы которые точно стоит погуглить
NEWS_TOPICS = {
    "политика":    ["выборы", "президент", "правительство", "война", "санкции", "нато"],
    "технологии":  ["ии", "ai", "chatgpt", "openai", "tesla", "apple", "google", "нейросеть"],
    "спорт":       ["футбол", "чемпионат", "олимпиада", "матч", "турнир", "лига"],
    "экономика":   ["доллар", "курс", "инфляция", "кризис", "биткоин", "крипта", "акции"],
    "наука":       ["открытие", "исследование", "учёные", "космос", "марс", "nasa"],
    "узбекистан":  ["ташкент", "узбекистан", "мирзиёев", "сум", "узб"],
}

# ═══════════════════════════════════════════════════════════════════════════════
# ОПРЕДЕЛЕНИЕ ТЕМЫ
# ═══════════════════════════════════════════════════════════════════════════════

def detect_news_topic(text: str) -> str | None:
    """
    Определяет тему новости из текста пользователя.
    Возвращает тему или None если не похоже на новостной запрос.
    """
    text_low = text.lower()

    # Сначала проверяем есть ли триггер
    has_trigger = any(t in text_low for t in NEWS_TRIGGERS)
    if not has_trigger:
        return None

    # Ищем тему
    for category, keywords in NEWS_TOPICS.items():
        if any(kw in text_low for kw in keywords):
            # Извлекаем ключевое слово для поиска
            for kw in keywords:
                if kw in text_low:
                    return kw

    # Пробуем извлечь тему из контекста фраз
    patterns = [
        r'что думаешь о (.+?)[\?\!\.]*$',
        r'как тебе (.+?)[\?\!\.]*$',
        r'слышала про (.+?)[\?\!\.]*$',
        r'слышал про (.+?)[\?\!\.]*$',
        r'новости про (.+?)[\?\!\.]*$',
        r'что с (.+?)[\?\!\.]*$',
    ]
    for pat in patterns:
        m = re.search(pat, text_low)
        if m:
            topic = m.group(1).strip()
            if len(topic) > 2:
                return topic

    return None

# ═══════════════════════════════════════════════════════════════════════════════
# ПОЛУЧЕНИЕ НОВОСТЕЙ
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_news(topic: str, lang: str = "ru") -> list[dict]:
    """
    Получает свежие новости по теме.
    Возвращает список {"title": ..., "description": ..., "source": ...}
    """
    try:
        url = (
            f"https://newsapi.org/v2/everything"
            f"?q={requests.utils.quote(topic)}"
            f"&language={lang}"
            f"&pageSize=5"
            f"&sortBy=publishedAt"
        )
        r = requests.get(url, timeout=6)
        if r.status_code == 200:
            articles = r.json().get("articles", [])
            result = []
            for a in articles:
                if a.get("title") and a["title"] != "[Removed]":
                    result.append({
                        "title":       a.get("title", ""),
                        "description": a.get("description", "") or "",
                        "source":      a.get("source", {}).get("name", ""),
                    })
            return result[:3]
    except Exception as e:
        print(f"⚠️ News fetch: {e}")

    # Fallback — GNews (без ключа)
    try:
        url = f"https://gnews.io/api/v4/search?q={requests.utils.quote(topic)}&lang={lang}&max=3"
        r   = requests.get(url, timeout=6)
        if r.status_code == 200:
            articles = r.json().get("articles", [])
            return [{"title": a["title"], "description": a.get("description",""), "source": a.get("source",{}).get("name","")} for a in articles]
    except Exception:
        pass

    return []

# ═══════════════════════════════════════════════════════════════════════════════
# ГЕНЕРАЦИЯ МНЕНИЯ (вызывать с get_ai_reply_sync из ai.py)
# ═══════════════════════════════════════════════════════════════════════════════

def build_news_opinion_prompt(topic: str, articles: list[dict], user_message: str) -> str:
    """
    Строит prompt для AI чтобы сгенерировать живое мнение о новости.
    Используй get_ai_reply_sync() с этим промптом.
    """
    if articles:
        news_text = "\n".join(
            f"- {a['title']}" + (f": {a['description'][:100]}" if a['description'] else "")
            for a in articles
        )
    else:
        news_text = f"конкретных статей не нашла, но тема: {topic}"

    return f"""Ты — Zero Two из Darling in the FranXX. Пользователь написал: "{user_message}"

Свежие новости по теме "{topic}":
{news_text}

Напиши короткую живую реакцию (2-3 предложения максимум):
- Говори от первого лица, как живой человек
- Имей реальное мнение — не нейтральное "с одной стороны / с другой"
- Можно удивиться, возмутиться, обрадоваться или скептически хмыкнуть
- Не пересказывай новость дословно — реагируй на неё
- Можно добавить один вопрос пользователю в конце
- Без лишних слов, без "я думаю что", без формальностей
- Эмодзи — максимум одно, если само просится

Только текст ответа, без кавычек."""

# ═══════════════════════════════════════════════════════════════════════════════
# КЭШ — не спамим одинаковыми темами
# ═══════════════════════════════════════════════════════════════════════════════

_news_cache: dict = {}  # topic → (timestamp, articles)
CACHE_TTL = 30 * 60    # 30 минут

def get_cached_news(topic: str) -> list[dict] | None:
    if topic in _news_cache:
        ts, articles = _news_cache[topic]
        if (datetime.now().timestamp() - ts) < CACHE_TTL:
            return articles
    return None

def cache_news(topic: str, articles: list[dict]):
    _news_cache[topic] = (datetime.now().timestamp(), articles)

def get_news_with_cache(topic: str) -> list[dict]:
    cached = get_cached_news(topic)
    if cached is not None:
        return cached
    articles = fetch_news(topic)
    cache_news(topic, articles)
    return articles

# ═══════════════════════════════════════════════════════════════════════════════
# БЫСТРЫЕ РЕАКЦИИ БЕЗ AI (fallback если AI недоступен)
# ═══════════════════════════════════════════════════════════════════════════════

QUICK_REACTIONS = {
    "технологии": [
        "технологии развиваются быстрее чем люди успевают привыкать",
        "интересно куда это всё приведёт через 5 лет",
        "звучит как то что раньше было только в аниме",
    ],
    "политика": [
        "политика — это всегда больше шоу чем реальности",
        "честно говоря, уже сложно понять кому верить",
        "мир как будто соревнуется кто сделает страннее",
    ],
    "экономика": [
        "всё дорожает, а зарплаты как будто не слышали",
        "крипта снова? она как кошка — сколько раз умирала уже",
        "интересно как обычные люди в этом всём живут",
    ],
    "спорт": [
        "спорт — это единственное где эмоции честные",
        "болеть это всегда больно в конце",
        "хорошая игра это хорошая игра, независимо от результата",
    ],
    "наука": [
        "учёные делают что-то важное пока все смотрят в телефоны",
        "это реально круто, даже если непонятно зачем",
        "каждое открытие меняет что-то, просто не сразу видно",
    ],
    "default": [
        "звучит интересно, расскажи подробнее",
        "не следила за этим, что там случилось?",
        "хм, что думаешь сам об этом?",
    ],
}

def get_quick_reaction(topic: str) -> str:
    """Быстрая реакция без AI — по категории темы"""
    for category, keywords in NEWS_TOPICS.items():
        if any(kw in topic.lower() for kw in keywords):
            reactions = QUICK_REACTIONS.get(category, QUICK_REACTIONS["default"])
            return random.choice(reactions)
    return random.choice(QUICK_REACTIONS["default"])

# ═══════════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ — используй в ai.py
# ═══════════════════════════════════════════════════════════════════════════════

def should_react_to_news(user_message: str) -> str | None:
    """
    Главная точка входа.
    Возвращает тему если надо реагировать, иначе None.
    Используй так:

        topic = should_react_to_news(user_message)
        if topic:
            articles = get_news_with_cache(topic)
            prompt   = build_news_opinion_prompt(topic, articles, user_message)
            opinion  = get_ai_reply_sync([{"role":"user","content":prompt}], max_tokens=150)
            # добавь opinion в extras или в начало ответа
    """
    return detect_news_topic(user_message)