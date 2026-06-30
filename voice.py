"""
voice.py — голосовые сообщения с эмоцией.
Порядок: edge-tts → Google Cloud TTS (SSML) → Silero → gTTS
Тон голоса меняется в зависимости от настроения бота и пользователя.
"""

import os, re, asyncio, tempfile, json
from config import VOICE

# ── Google Cloud credentials ───────────────────────────────────────────────────
_creds_json = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON")
if _creds_json:
    _tmp_creds = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    _tmp_creds.write(_creds_json)
    _tmp_creds.close()
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _tmp_creds.name
else:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "kamilla-bot-498611-abcb63a2468e.json"

# ═══════════════════════════════════════════════════════════════════════════════
# ПРОФИЛИ ЭМОЦИЙ
# ═══════════════════════════════════════════════════════════════════════════════

EMOTION_PROFILES = {

    # ── Радость / энергия ──────────────────────────────────────────────────────
    "joy": {
        "speaking_rate": 1.00,
        "pitch":         2.0,
        "volume_gain_db": 2.0,
        "ssml_rate":     "medium",
        "description":   "радостная, энергичная",
    },
    "excitement": {
        "speaking_rate": 1.05,
        "pitch":         3.0,
        "volume_gain_db": 2.5,
        "ssml_rate":     "medium",
        "description":   "взволнованная",
    },
    "playful": {
        "speaking_rate": 0.95,
        "pitch":         2.5,
        "volume_gain_db": 1.5,
        "ssml_rate":     "medium",
        "description":   "игривая",
    },

    # ── Нежность / близость ───────────────────────────────────────────────────
    "love": {
        "speaking_rate": 0.80,
        "pitch":         1.5,
        "volume_gain_db": 0.5,
        "ssml_rate":     "slow",
        "description":   "нежная, тёплая",
    },
    "warm": {
        "speaking_rate": 0.83,
        "pitch":         1.5,
        "volume_gain_db": 1.0,
        "ssml_rate":     "slow",
        "description":   "тёплая",
    },
    "care": {
        "speaking_rate": 0.78,
        "pitch":         1.0,
        "volume_gain_db": 0.5,
        "ssml_rate":     "slow",
        "description":   "заботливая",
    },

    # ── Грусть / поддержка ────────────────────────────────────────────────────
    "sadness": {
        "speaking_rate": 0.75,
        "pitch":        -1.0,
        "volume_gain_db": 0.0,
        "ssml_rate":     "slow",
        "description":   "грустная, тихая",
    },
    "grief": {
        "speaking_rate": 0.72,
        "pitch":        -2.0,
        "volume_gain_db":-0.5,
        "ssml_rate":     "slow",
        "description":   "серьёзная, сочувствующая",
    },
    "loneliness": {
        "speaking_rate": 0.77,
        "pitch":        -1.5,
        "volume_gain_db": 0.0,
        "ssml_rate":     "slow",
        "description":   "тихая, задумчивая",
    },

    # ── Обида / холод ─────────────────────────────────────────────────────────
    "offended": {
        "speaking_rate": 0.85,
        "pitch":        -0.5,
        "volume_gain_db":-1.0,
        "ssml_rate":     "medium",
        "description":   "сухая, обиженная",
    },
    "cold": {
        "speaking_rate": 0.90,
        "pitch":        -2.0,
        "volume_gain_db":-2.0,
        "ssml_rate":     "medium",
        "description":   "холодная, отстранённая",
    },

    # ── Злость / тревога ──────────────────────────────────────────────────────
    "anger": {
        "speaking_rate": 1.00,
        "pitch":        -1.0,
        "volume_gain_db": 2.0,
        "ssml_rate":     "medium",
        "description":   "резкая",
    },
    "anxiety": {
        "speaking_rate": 1.02,
        "pitch":         1.0,
        "volume_gain_db": 1.0,
        "ssml_rate":     "medium",
        "description":   "взволнованная, напряжённая",
    },

    # ── Время суток ───────────────────────────────────────────────────────────
    "morning": {
        "speaking_rate": 0.78,
        "pitch":         0.5,
        "volume_gain_db": 0.5,
        "ssml_rate":     "slow",
        "description":   "сонная, мягкая",
    },
    "evening": {
        "speaking_rate": 0.82,
        "pitch":         1.0,
        "volume_gain_db": 0.5,
        "ssml_rate":     "slow",
        "description":   "расслабленная, вечерняя",
    },
    "late_night": {
        "speaking_rate": 0.88,
        "pitch":        1.5,
        "volume_gain_db":-1.0,
        "ssml_rate":     "x-slow",
        "description":   "тихая, ночная",
    },

    # ── По умолчанию ──────────────────────────────────────────────────────────
    "normal": {
        "speaking_rate": 0.92,
        "pitch":         3.0,
        "volume_gain_db": 1.0,
        "ssml_rate":     "slow",
        "description":   "обычная",
    },
}

def get_emotion_profile(emotion: str | None) -> dict:
    if not emotion:
        return EMOTION_PROFILES["normal"]
    return EMOTION_PROFILES.get(emotion, EMOTION_PROFILES["normal"])

# ═══════════════════════════════════════════════════════════════════════════════
# ОПРЕДЕЛЕНИЕ ЭМОЦИИ ПО КОНТЕКСТУ
# ═══════════════════════════════════════════════════════════════════════════════

def detect_voice_emotion(
    text: str,
    bot_mood: str = "normal",
    user_emotion: str = None,
    hour: int = None,
) -> str:
    from datetime import datetime
    from config import TZ

    if hour is None:
        hour = datetime.now(TZ).hour

    text_low = text.lower()

    # 1. Настроение бота — приоритет
    if bot_mood == "cold":
        return "cold"
    if bot_mood == "offended":
        return "offended"
    if bot_mood == "warm":
        return "warm"

    # 2. Время суток
    if 0 <= hour <= 6:
        return "late_night"
    if 7 <= hour <= 9:
        return "morning"
    if 20 <= hour <= 23:
        return "evening"

    # 3. Ключевые слова в тексте
    joy_words  = ["смеш", "хаха", "ахах", "весел", "классно", "отлично", "ура", "🔥", "😂", "🎉"]
    love_words = ["скучаю", "скучала", "дарлинг", "любим", "рядом", "обним", "❤️", "💜"]
    care_words = ["держись", "всё будет", "не грусти", "понимаю", "слышу тебя", "бывает"]
    sad_words  = ["грустно", "жаль", "обидно", "тяжело", "сочувствую", "больно"]
    play_words = ["хе-хе", "хитр", "прикол", "ладно-ладно", "ну ты", "😏", "👀"]

    if any(w in text_low for w in joy_words):  return "joy"
    if any(w in text_low for w in love_words): return "love"
    if any(w in text_low for w in care_words): return "care"
    if any(w in text_low for w in sad_words):  return "sadness"
    if any(w in text_low for w in play_words): return "playful"

    # 4. Зеркалим эмоцию пользователя
    emotion_mirror = {
        "joy":        "joy",
        "excitement": "excitement",
        "sadness":    "care",
        "grief":      "grief",
        "loneliness": "loneliness",
        "anger":      "normal",
        "anxiety":    "care",
        "love":       "love",
    }
    if user_emotion and user_emotion in emotion_mirror:
        return emotion_mirror[user_emotion]

    return "normal"

# ═══════════════════════════════════════════════════════════════════════════════
# ПОДГОТОВКА ТЕКСТА ДЛЯ TTS
# ═══════════════════════════════════════════════════════════════════════════════

def _clean_for_tts(text: str) -> str:
    """Убирает markdown, эмодзи, лишние символы. Оставляет пунктуацию для пауз."""
    clean = re.sub(r'\*+', '', text)
    clean = re.sub(r'_+', '', clean)
    clean = re.sub(r'`+', '', clean)
    # Убираем эмодзи и спецсимволы, сохраняем кириллицу, латиницу, пунктуацию
    clean = re.sub(r'[^\w\s.,!?;:\-\u0400-\u04FF]', '', clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean

def _add_pauses_for_edge(text: str) -> str:
    """Добавляет дополнительные пробелы после знаков — edge-tts делает на них паузы."""
    text = re.sub(r'([.!?])\s+', r'\1  ', text)
    text = re.sub(r'([,;])\s+', r'\1 ', text)
    return text

def _build_ssml(text: str, profile: dict) -> str:
    """SSML для Google Cloud TTS."""
    clean = _clean_for_tts(text)
    # Паузы через SSML break
    clean = re.sub(r'([.!?])\s+', r'\1 <break time="450ms"/> ', clean)
    clean = re.sub(r'([,;])\s+', r'\1 <break time="200ms"/> ', clean)

    rate = profile.get("ssml_rate", "slow")
    pitch_st = int(profile.get("pitch", 0.5))
    pitch_str = f"{pitch_st:+d}st" if pitch_st != 0 else "0st"

    return (
        f'<speak>'
        f'<prosody rate="{rate}" pitch="{pitch_str}">'
        f'{clean}'
        f'</prosody>'
        f'</speak>'
    )

# ═══════════════════════════════════════════════════════════════════════════════
# ОСНОВНАЯ ФУНКЦИЯ TTS
# ═══════════════════════════════════════════════════════════════════════════════

async def text_to_voice(
    text: str,
    emotion: str = None,
    bot_mood: str = "normal",
    user_emotion: str = None,
) -> str | None:
    """
    Порядок: edge-tts → Google Cloud TTS → Silero → gTTS
    Возвращает путь к файлу или None если всё упало.
    """
    clean_text = _clean_for_tts(text)
    if not clean_text:
        return None

    if not emotion:
        emotion = detect_voice_emotion(text, bot_mood=bot_mood, user_emotion=user_emotion)

    profile = get_emotion_profile(emotion)
    print(f"🎙 Эмоция голоса: {emotion} ({profile['description']})")

    # 1. edge-tts — лучшее качество без API ключей
    result = await _try_edge_tts(clean_text, profile)
    if result:
        return result

    # 2. Google Cloud TTS с SSML
    result = await _try_google_tts(clean_text, profile)
    if result:
        return result

    # 3. Silero офлайн
    result = await _try_silero(clean_text)
    if result:
        return result

    # 4. gTTS — последний резерв, без настроек
    result = await _try_gtts(clean_text)
    if result:
        return result

    print("⚠️ Все TTS движки недоступны")
    return None

# ═══════════════════════════════════════════════════════════════════════════════
# edge-tts — ПЕРВЫЙ ПРИОРИТЕТ
# ═══════════════════════════════════════════════════════════════════════════════

# Голоса от живее к менее живому
EDGE_VOICES = [
    "ru-RU-DariyaNeural",    # молодой живой голос
    "ru-RU-SvetlanaNeural",  # запасной
]

async def _try_edge_tts(text: str, profile: dict = None) -> str | None:
    try:
        import edge_tts
        if profile is None:
            profile = EMOTION_PROFILES["normal"]

        rate  = profile.get("speaking_rate", 0.92)
        pitch = profile.get("pitch", 3.0)

        rate_pct = int((rate - 1.0) * 100)
        pitch_hz = max(10, int(pitch * 4))  # минимум 10Hz чтобы не было ошибки

        rate_str  = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"
        pitch_str = f"+{pitch_hz}Hz"

        text_prepared = _add_pauses_for_edge(text)

        for voice in EDGE_VOICES:
            tmp_path = None
            try:
                tmp      = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
                tmp_path = tmp.name
                tmp.close()

                communicate = edge_tts.Communicate(
                    text_prepared,
                    voice,
                    rate=rate_str,
                    pitch=pitch_str,
                )
                await asyncio.wait_for(communicate.save(tmp_path), timeout=30)

                if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 1000:
                    print(f"🎙 edge-tts ✅ {voice} (rate={rate_str}, pitch={pitch_str})")
                    return tmp_path
                else:
                    try: os.unlink(tmp_path)
                    except: pass

            except asyncio.TimeoutError:
                print(f"⚠️ edge-tts таймаут ({voice})")
                if tmp_path:
                    try: os.unlink(tmp_path)
                    except: pass
                continue
            except Exception as e:
                print(f"⚠️ edge-tts {voice}: {e}")
                if tmp_path:
                    try: os.unlink(tmp_path)
                    except: pass
                continue

        return None

    except ImportError:
        print("⚠️ edge-tts не установлен: pip install edge-tts")
        return None
    except Exception as e:
        print(f"⚠️ edge-tts: {e}")
        return None
# ═══════════════════════════════════════════════════════════════════════════════
# GOOGLE CLOUD TTS
# ═══════════════════════════════════════════════════════════════════════════════

async def _try_google_tts(text: str, profile: dict) -> str | None:
    try:
        from google.cloud import texttospeech
        loop = asyncio.get_event_loop()
        ssml = _build_ssml(text, profile)

        def _synthesize():
            tts_client = texttospeech.TextToSpeechClient()
            synthesis_input = texttospeech.SynthesisInput(ssml=ssml)
            voice = texttospeech.VoiceSelectionParams(
                language_code="ru-RU",
                name="ru-RU-Wavenet-E",
                ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=profile.get("speaking_rate", 0.83),
                pitch=profile.get("pitch", 0.5),
                volume_gain_db=profile.get("volume_gain_db", 1.0),
                effects_profile_id=["telephony-class-application"],
            )
            response = tts_client.synthesize_speech(
                input=synthesis_input,
                voice=voice,
                audio_config=audio_config
            )
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.write(response.audio_content)
            tmp.close()
            return tmp.name

        path = await loop.run_in_executor(None, _synthesize)
        if path and os.path.exists(path) and os.path.getsize(path) > 1000:
            print("🎙 Google Cloud TTS ✅")
            return path
        return None
    except ImportError:
        return None
    except Exception as e:
        print(f"⚠️ Google Cloud TTS: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# SILERO
# ═══════════════════════════════════════════════════════════════════════════════

_silero_model = None

def _get_silero_model():
    global _silero_model
    if _silero_model is not None:
        return _silero_model
    try:
        import torch
        model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-models",
            model="silero_tts",
            language="ru",
            speaker="v3_1_ru"
        )
        model.eval()
        _silero_model = model
        print("🎙 Silero модель загружена ✅")
        return model
    except Exception as e:
        print(f"⚠️ Silero загрузка: {e}")
        return None

async def _try_silero(text: str) -> str | None:
    try:
        import torch
        import soundfile as sf
        loop = asyncio.get_event_loop()

        def _synthesize():
            model = _get_silero_model()
            if model is None:
                return None
            audio = model.apply_tts(
                text=text,
                speaker="baya",
                sample_rate=48000,
                put_accent=True,
                put_yo=True
            )
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            sf.write(tmp.name, audio.numpy(), 48000)
            tmp.close()
            return tmp.name

        path = await loop.run_in_executor(None, _synthesize)
        if path and os.path.exists(path) and os.path.getsize(path) > 1000:
            print("🎙 Silero ✅")
            return path
        return None
    except ImportError:
        return None
    except Exception as e:
        print(f"⚠️ Silero: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# gTTS — ПОСЛЕДНИЙ РЕЗЕРВ
# ═══════════════════════════════════════════════════════════════════════════════

async def _try_gtts(text: str) -> str | None:
    try:
        from gtts import gTTS
        loop = asyncio.get_event_loop()

        def _synthesize():
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()
            tts = gTTS(text=text, lang="ru", slow=True)  # slow=True хотя бы немного медленнее
            tts.save(tmp.name)
            return tmp.name

        path = await loop.run_in_executor(None, _synthesize)
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            print("🎙 gTTS ✅ (резерв)")
            return path
        return None
    except ImportError:
        return None
    except Exception as e:
        print(f"⚠️ gTTS: {e}")
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# КОГДА ОТПРАВЛЯТЬ ГОЛОС
# ═══════════════════════════════════════════════════════════════════════════════

VOICE_EMOTION_TRIGGERS = [
    "скучаю", "думаю о тебе", "доброе утро", "добрый вечер",
    "не грусти", "ты молодец", "напоминаю", "скучала", "соскучилась",
    "плачу", "грустно", "одиноко", "тяжело", "больно",
    "счастлив", "получилось", "рад", "держись",
    "люблю", "дорогой", "дарлинг", "любимый", "рядом",
]

def should_send_voice(
    text: str,
    user_message: str = "",
    emotion: str = None,
    bot_mood: str = "normal",
) -> bool:
    import random

    # Явный запрос голосового
    voice_requests = ["голосовое", "голосом", "запиши", "скажи голосом", "ovozli", "voice", "audio"]
    if any(t in user_message.lower() for t in voice_requests):
        return True

    text_low = text.lower()

    # Холодное настроение — голос не отправляем
    if bot_mood == "cold":
        return False
    if bot_mood == "offended":
        return random.random() < 0.10

    # Эмоциональный триггер в тексте бота
    if any(t in text_low for t in VOICE_EMOTION_TRIGGERS):
        return random.random() < 0.50

    # Сильная эмоция пользователя
    if emotion in ("grief", "loneliness", "sadness", "joy"):
        return random.random() < 0.35

    # Проактивное сообщение
    proactive_triggers = ["скучала", "думала о тебе", "вспомнила", "соскучилась"]
    if any(t in text_low for t in proactive_triggers):
        return random.random() < 0.30

    return False
