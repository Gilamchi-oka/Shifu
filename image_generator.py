"""
image_generator.py — генерация изображений через Pollinations.ai
Бесплатно, без API ключей. Подключается в main.py и ai.py
"""

import asyncio
import re
import urllib.parse
import aiohttp

# ── URL Pollinations ──────────────────────────────────────────────────────────

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"

# ── Триггеры на запрос картинки ───────────────────────────────────────────────

IMAGE_TRIGGERS = [
    "нарисуй",
    "сгенерируй фото", "сгенерируй картинку", "сгенерируй изображение",
    "создай картинку", "создай изображение", "создай фото",
    "сделай картинку", "сделай фото", "сделай изображение",
    "нарисуй мне", "покажи как выглядит", "покажи как выглядят",
    "визуализируй", "покажи картинку", "покажи фото",
    "отправь фото", "пришли фото",
    "draw me", "generate image", "show me picture",
    "хочу видеть картинку", "хочу картинку",
]

# Стоп-слова — не генерируем если это не про арт
IMAGE_STOP_WORDS = [
    "своё фото", "твоё фото", "твою фотографию",
    "фото себя", "твоё настоящее фото", "как ты выглядишь",
]

# Стили генерации
STYLES = {
    "anime":     "beautiful anime art, detailed, vibrant colors, high quality, studio ghibli style,",
    "realistic": "photorealistic, ultra detailed, 8k, cinematic lighting,",
    "art":       "digital art, artistic, creative, concept art,",
    "cute":      "cute kawaii style, soft colors, adorable,",
    "dark":      "dark fantasy art, dramatic lighting, moody,",
}


def is_image_request(text: str) -> str | None:
    """
    Проверяет является ли сообщение запросом на генерацию изображения.
    Возвращает промпт (что рисовать) или None.
    """
    text_low = text.lower().strip()

    # Сначала проверяем стоп-слова
    if any(stop in text_low for stop in IMAGE_STOP_WORDS):
        return None

    for trigger in IMAGE_TRIGGERS:
        if trigger in text_low:
            # Извлекаем что нарисовать — убираем триггер и мусор
            prompt = text_low
            for t in sorted(IMAGE_TRIGGERS, key=len, reverse=True):
                prompt = prompt.replace(t, "")
            prompt = re.sub(r'^[\s,.:!?]+', '', prompt).strip()
            prompt = re.sub(r'^(мне|мне,|нам|пожалуйста|пж|please|ка)\s*', '', prompt).strip()

            # Если после чистки почти ничего не осталось — дефолтный промпт
            if len(prompt) < 3:
                prompt = "zero two darling in the franxx anime girl"

            return prompt

    return None


def detect_style(prompt: str) -> str:
    """Определяет стиль по промпту"""
    p = prompt.lower()
    if any(w in p for w in ["аниме", "anime", "манга", "zero two", "дарлинг"]):
        return "anime"
    if any(w in p for w in ["реалистич", "realistic", "фото", "real"]):
        return "realistic"
    if any(w in p for w in ["милый", "kawaii", "cute", "кавай"]):
        return "cute"
    if any(w in p for w in ["тёмный", "dark", "мрачный", "страшный"]):
        return "dark"
    return "anime"  # дефолт — аниме стиль под персонажа бота


def build_prompt(user_prompt: str, style: str | None = None) -> str:
    """Строит финальный промпт для Pollinations"""
    if style is None:
        style = detect_style(user_prompt)

    style_prefix = STYLES.get(style, STYLES["anime"])

    # Переводим ключевые русские слова в английские для лучшего результата
    translations = {
        "кот": "cat", "кошка": "cat", "собака": "dog", "пёс": "dog",
        "закат": "sunset", "рассвет": "sunrise", "море": "ocean",
        "лес": "forest", "горы": "mountains", "город": "city",
        "девушка": "girl", "парень": "boy", "дракон": "dragon",
        "цветы": "flowers", "цветок": "flower", "небо": "sky",
        "звёзды": "stars", "луна": "moon", "солнце": "sun",
        "замок": "castle", "дом": "house", "машина": "car",
        "красивый": "beautiful", "тёмный": "dark", "яркий": "bright",
        "грустный": "sad", "счастливый": "happy", "милый": "cute",
    }

    prompt = user_prompt.lower()
    for ru, en in translations.items():
        prompt = prompt.replace(ru, en)

    return f"{style_prefix} {prompt}, masterpiece, best quality"


async def generate_image(
    prompt: str,
    style: str | None = None,
    width: int = 768,
    height: int = 768,
) -> str | None:
    """
    Генерирует изображение через Pollinations.ai.
    Возвращает путь к временному файлу или None при ошибке.
    """
    full_prompt = build_prompt(prompt, style)
    encoded     = urllib.parse.quote(full_prompt)
    url         = (
        f"{POLLINATIONS_URL.format(prompt=encoded)}"
        f"?width={width}&height={height}&nologo=true&enhance=true&seed={abs(hash(prompt)) % 99999}"
    )

    print(f"🎨 Генерирую: {prompt[:50]}...")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                if resp.status == 200:
                    content = await resp.read()
                    if len(content) < 5000:
                        # Слишком маленький файл — скорее всего ошибка
                        print("⚠️ Pollinations: файл слишком маленький")
                        return None
                    path = f"/tmp/gen_{abs(hash(prompt)) % 999999}.jpg"
                    with open(path, "wb") as f:
                        f.write(content)
                    print(f"✅ Изображение: {path} ({len(content)//1024}KB)")
                    return path
                else:
                    print(f"⚠️ Pollinations: HTTP {resp.status}")
    except asyncio.TimeoutError:
        print("⚠️ Pollinations: timeout (45s)")
    except Exception as e:
        print(f"⚠️ Pollinations error: {e}")

    return None


# ── Фразы пока рисуется ───────────────────────────────────────────────────────

GENERATION_PHRASES = [
    "рисую... подожди немного 🎨",
    "уже создаю, секунду 🖼",
    "генерирую... чуть-чуть подожди ✨",
    "творю кое-что для тебя...",
    "работаю над этим 🖌",
]

PHOTO_RECEIVED_PHRASES = [
    "ой, интересно 👀 что это за фото?",
    "вижу картинку — расскажи про неё?",
    "хм, что хотел показать?",
    "о, фото! что это такое?",
    "посмотрела... и что мне с этим делать? 😄",
]

GENERATION_FAIL_PHRASES = [
    "что-то не получилось нарисовать 😔 попробуй позже",
    "художник из меня сегодня никакой... попробуй ещё раз",
    "не вышло 😕 можешь переформулировать?",
]