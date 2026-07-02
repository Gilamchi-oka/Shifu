"""
main.py — запуск бота, Telegram handler, scheduler
"""

import asyncio
import random
import os
import re
import base64
import json
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeAudio
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import (
    API_ID, API_HASH, TZ, ADMIN_ID,
    PROACTIVE_USERS, PROACTIVE_MESSAGES,
    MORNING_MSGS, EVENING_MSGS, FACTS, QUOTES,
    HOLIDAYS, GROQ_KEYS, ELEVEN_KEYS, VOICE,
    MEMORY_FILE, TASKS_FILE, STATS_FILE, HISTORY_FILE, STYLE_FILE,
    WAKE_UP_MSGS, RUN_REMINDER_MSGS, PRAYER_REMINDER_MSGS,
    SCHEDULE_PLAN_MSGS, BREAKFAST_MSGS, LUNCH_MSGS,
    EVENING_TRAINING_MSGS, SLEEP_REMINDER_MSGS, LATE_NIGHT_MSGS,
    TRAINING_DAYS, POOL_DAY,
)
from memory import (
    update_stats, get_stats_text, get_user_memory,
    load_json, save_json_local, github_download, autosave_to_github,
    flush_uploads, load_history
)
from ai import (
    get_reply, summarize_all, write_diary_entry, conversations,
    last_proactive, voice_requested, user_18plus_mode,
    get_ai_reply_sync, detect_tool_calls
)
from tools import (
    parse_commands, clear_user_tasks, load_tasks, save_tasks,
    get_current_time, stopwatch_start, stopwatch_stop, stopwatch_status,
    add_expense, get_expenses_today, get_expenses_month, get_daily_budget_summary,
    lang_start, lang_stop, lang_next_word, lang_check_answer,
    lang_stats, is_lang_active,
)
from voice import text_to_voice, should_send_voice
from personality import user_moods, SYSTEM_PROMPT
from humanizer import humanize_and_send, get_time_factor
from activity_tracker import record_activity, is_user_likely_active, get_activity_summary, get_mood_by_weekday

from mood_tracker import get_current_mood, get_mood_reaction
from followup_tracker import get_pending_followups, clear_old_followups
from diary import get_diary_stats
from mood_predictor import get_predictor_stats

from image_generator import (
    is_image_request, generate_image,
    GENERATION_PHRASES, PHOTO_RECEIVED_PHRASES, GENERATION_FAIL_PHRASES
)
from games import (
    detect_game_start, detect_game_stop,
    handle_game_input, start_game, stop_game,
    is_game_active,
)

from telethon.sessions import StringSession

SESSION_STRING = os.getenv("SESSION_STRING")
client    = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
scheduler = AsyncIOScheduler(timezone=TZ)

# ── Состояние ─────────────────────────────────────────────────────────────────

last_user_message:    dict = {}
last_proactive_topic: dict = {}
last_messages:        dict = {}

# ── Праздники ─────────────────────────────────────────────────────────────────

def get_holiday_message() -> str | None:
    now = datetime.now(TZ)
    return HOLIDAYS.get((now.month, now.day))

# ── Задержка печати ───────────────────────────────────────────────────────────

def calc_typing_delay(text: str) -> float:
    words = len(text.split())
    if words <= 5:    return random.uniform(2, 4)
    elif words <= 15: return random.uniform(5, 10)
    elif words <= 30: return random.uniform(10, 20)
    else:             return random.uniform(20, 40)

# ── Базовая отправка одного сообщения ────────────────────────────────────────

async def _send_one(chat_id: int, text: str, reply_to=None, user_message: str = ""):
    if not text:
        return
    if reply_to:
        await reply_to.reply(text)
    else:
        await client.send_message(chat_id, text)

# ── Умная отправка через humanizer ───────────────────────────────────────────

async def send_message_smart(chat_id: int, text: str, reply_to=None, user_message: str = ""):
    if not text:
        return

    async def _sender(cid, msg, reply_to=None, user_message=""):
        async with client.action(cid, "typing"):
            await _send_one(cid, msg, reply_to=reply_to, user_message=user_message)

    await humanize_and_send(
        send_func=_sender,
        chat_id=chat_id,
        text=text,
        reply_to=reply_to,
        user_message=user_message
    )

# ── Генерация умного проактивного сообщения через AI ─────────────────────────

def generate_proactive_message(user_id: int, reason: str) -> str:
    mem  = get_user_memory(user_id)
    now  = datetime.now(TZ)
    hour = now.hour

    context_parts = []
    if mem.get("name"):            context_parts.append(f"Его зовут {mem['name']}")
    if mem.get("interests"):       context_parts.append(f"Интересы: {', '.join(mem['interests'][:4])}")
    if mem.get("goals"):           context_parts.append(f"Его цели: {', '.join(mem['goals'][:3])}")
    if mem.get("last_topic"):      context_parts.append(f"Последняя тема разговора: {mem['last_topic']}")
    if mem.get("unfinished"):      context_parts.append(f"Незакрытая тема: {mem['unfinished']}")
    if mem.get("current_emotion"): context_parts.append(f"Последняя эмоция: {mem['current_emotion']}")
    if mem.get("city"):            context_parts.append(f"Город: {mem['city']}")

    context = "\n".join(context_parts) if context_parts else "Пользователь почти незнаком"

    reason_map = {
        "silence_6h":  "пользователь не писал 6+ часов, хочется напомнить о себе",
        "silence_12h": "пользователь не писал полдня, соскучилась",
        "silence_24h": "пользователь не писал целый день",
        "morning":     f"утро ({hour}:00), хочется поздороваться по-живому",
        "evening":     f"вечер ({hour}:00), хочется узнать как прошёл день",
        "random":      "просто захотелось написать, настроение такое",
        "goal_check":  "хочется ненавязчиво спросить про его цель/планы",
        "unfinished":  "хочется вернуться к незакрытой теме разговора",
        "late_night":  f"поздно ночью ({hour}:00), замечаешь что он не спит",
    }
    reason_text = reason_map.get(reason, reason)
    prev_topic  = last_proactive_topic.get(user_id, "")

    prompt = f"""Ты — Zero Two из Darling in the FranXX. Пишешь пользователю первой в Telegram.

Что знаешь о нём:
{context}

Причина: {reason_text}
{f'Не повторяй тему: {prev_topic}' if prev_topic else ''}

Напиши ОДНО короткое живое сообщение (3-10 слов, максимум 15).
Правила:
- Говори как живой человек, не как бот
- Никаких списков и длинных объяснений
- Можно с лёгкой дерзостью, теплом, загадочностью
- "любимый" — только если уместно, не обязательно
- Эмодзи — максимум одно, и только если само просится
- Не начинай с "Привет" если причина не утро
- Опирайся на то что знаешь о нём — сделай сообщение личным

Только текст сообщения, без кавычек."""

    try:
        reply = get_ai_reply_sync(
            [{"role": "user", "content": prompt}],
            temperature=1.0,
            max_tokens=60
        )
        last_proactive_topic[user_id] = reply[:30]
        return reply.strip()
    except Exception as e:
        print(f"⚠️ Генерация проактивного: {e}")
        return random.choice(PROACTIVE_MESSAGES)

# ── Определить причину проактивного сообщения ────────────────────────────────

def get_proactive_reason(user_id: int) -> str | None:
    now  = datetime.now(TZ)
    hour = now.hour
    mem  = get_user_memory(user_id)

    if 0 <= hour < 8:
        return None

    last_msg      = last_user_message.get(user_id)
    silence_hours = (now - last_msg).total_seconds() / 3600 if last_msg else 999

    if 23 <= hour and last_msg and silence_hours < 1:
        return "late_night"

    if silence_hours >= 24:
        return "silence_24h"
    if silence_hours >= 12:
        return "silence_12h"
    if silence_hours >= 6:
        return "silence_6h"

    today = now.strftime("%d.%m.%Y")
    if (mem.get("unfinished") and
            mem.get("last_conversation_date") != today and
            random.random() > 0.5):
        return "unfinished"

    if mem.get("goals") and random.random() > 0.7:
        return "goal_check"

    if random.random() > 0.6:
        return "random"

    return None

# ── Напоминания ───────────────────────────────────────────────────────────────

async def send_reminder(user_id: int, text: str) -> bool:
    msgs = [
        f"⏰ напоминаю: {text}",
        f"Господин, ты просил напомнить: {text}",
        f"🔔 {text}",
    ]
    try:
        entity = await client.get_input_entity(user_id)
        await client.send_message(entity, random.choice(msgs))
        print(f"✅ Напоминание отправлено {user_id}: {text[:30]}")
        return True
    except ValueError:
        print(f"⚠️ Не могу найти entity для {user_id}, пропускаю напоминание")
        return False
    except Exception as e:
        print(f"⚠️ send_reminder error для {user_id}: {e}")
        return False


async def check_tasks():
    tasks   = load_tasks()
    now     = datetime.now(TZ)
    today   = now.strftime("%Y-%m-%d")
    updated = False

    for task in tasks:
        if task.get("repeat") == "daily" and task.get("time"):
            last_sent = task.get("last_sent_date")
            if last_sent == today:
                continue

            try:
                hour, minute = map(int, task["time"].split(":"))
            except Exception:
                continue

            task_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            diff_minutes = (now - task_time).total_seconds() / 60

            # окно "догонки" расширено: сработает в любой момент
            # от назначенного времени до 6 часов после, а не только 2 минуты
            if 0 <= diff_minutes <= 360:
                sent = await send_reminder(task["user_id"], task["text"])
                if sent:
                    task["last_sent_date"] = today
                    updated = True
                # если не отправилось — last_sent_date не ставится → попробует снова через минуту

        elif task.get("remind_at") and not task.get("done"):
            try:
                remind_at = datetime.fromisoformat(task["remind_at"])
                if remind_at.tzinfo is None:
                    remind_at = TZ.localize(remind_at)
            except Exception:
                continue

            if now >= remind_at:
                sent = await send_reminder(task["user_id"], task["text"])
                if sent:
                    task["done"] = True
                    updated = True

    if updated:
        save_tasks(tasks)
    if updated:
        save_tasks(tasks)


async def check_birthdays():
    memory = load_json(MEMORY_FILE)
    today  = datetime.now(TZ)
    for uid, data in memory.items():
        bday = data.get("birthday")
        if bday:
            try:
                bd = datetime.strptime(bday, "%d.%m")
                if bd.day == today.day and bd.month == today.month:
                    msg = generate_proactive_message(int(uid), "birthday")
                    await client.send_message(int(uid), f"🎂 {msg}")
            except Exception as e:
                print(f"Birthday error for {uid}: {e}")

# ── Проактивные сообщения ─────────────────────────────────────────────────────

async def proactive_message():
    if not PROACTIVE_USERS:
        return
    now = datetime.now(TZ)

    for user_id in PROACTIVE_USERS:
        last = last_proactive.get(user_id)
        if last and (now - last).total_seconds() < 40 * 60:
            continue

        if not is_user_likely_active(user_id):
            continue

        if random.random() > 0.25:
            continue

        reason = get_proactive_reason(user_id)
        if not reason:
            continue

        try:
            async with client.action(user_id, "typing"):
                msg   = generate_proactive_message(user_id, reason)
                delay = calc_typing_delay(msg)
                await asyncio.sleep(min(delay, 8))

            await send_message_smart(user_id, msg)
            last_proactive[user_id] = now
            print(f"💬 Проактивное ({reason}) → {user_id}: {msg}")
        except Exception as e:
            print(f"Proactive error: {e}")

# ── Утреннее/вечернее ─────────────────────────────────────────────────────────

async def morning_message():
    holiday = get_holiday_message()
    for user_id in PROACTIVE_USERS:
        try:
            msg = holiday if holiday else generate_proactive_message(user_id, "morning")
            async with client.action(user_id, "typing"):
                await asyncio.sleep(random.uniform(3, 7))
            await send_message_smart(user_id, msg)
            last_proactive[user_id] = datetime.now(TZ)
        except Exception as e:
            print(f"Morning: {e}")

# ── Расписание дня: жёсткие контрольные точки ─────────────────────────────────

async def wake_up_call():
    for user_id in PROACTIVE_USERS:
        try:
            await client.send_message(user_id, random.choice(WAKE_UP_MSGS))
        except Exception as e:
            print(f"Wake up: {e}")

async def run_reminder():
    for user_id in PROACTIVE_USERS:
        try:
            await client.send_message(user_id, random.choice(RUN_REMINDER_MSGS))
        except Exception as e:
            print(f"Run reminder: {e}")

async def prayer_reminder():
    for user_id in PROACTIVE_USERS:
        try:
            await client.send_message(user_id, random.choice(PRAYER_REMINDER_MSGS))
        except Exception as e:
            print(f"Prayer reminder: {e}")

async def schedule_plan_reminder():
    for user_id in PROACTIVE_USERS:
        try:
            await client.send_message(user_id, random.choice(SCHEDULE_PLAN_MSGS))
        except Exception as e:
            print(f"Schedule plan: {e}")

async def breakfast_reminder():
    for user_id in PROACTIVE_USERS:
        try:
            await client.send_message(user_id, random.choice(BREAKFAST_MSGS))
        except Exception as e:
            print(f"Breakfast: {e}")

async def lunch_reminder():
    for user_id in PROACTIVE_USERS:
        try:
            await client.send_message(user_id, random.choice(LUNCH_MSGS))
        except Exception as e:
            print(f"Lunch: {e}")

def _evening_block_kind() -> str:
    """Определяет тип вечернего блока по дню недели."""
    weekday = datetime.now(TZ).strftime("%A").lower()
    if weekday == POOL_DAY:
        return "pool"
    if weekday in TRAINING_DAYS:
        return "training"
    return "study"

async def evening_training_reminder():
    kind = _evening_block_kind()
    msg  = EVENING_TRAINING_MSGS.get(kind, EVENING_TRAINING_MSGS["study"])
    for user_id in PROACTIVE_USERS:
        try:
            await client.send_message(user_id, msg)
        except Exception as e:
            print(f"Evening training: {e}")

async def sleep_reminder():
    for user_id in PROACTIVE_USERS:
        try:
            await client.send_message(user_id, random.choice(SLEEP_REMINDER_MSGS))
        except Exception as e:
            print(f"Sleep reminder: {e}")

async def late_night_check():
    """Если ученик пишет после полуночи — Шифу это замечает."""
    now = datetime.now(TZ)
    if not (0 <= now.hour < 5):
        return
    for user_id in PROACTIVE_USERS:
        try:
            last_msg = last_user_message.get(user_id)
            if last_msg and (now - last_msg).total_seconds() < 1800:
                await client.send_message(user_id, random.choice(LATE_NIGHT_MSGS))
        except Exception as e:
            print(f"Late night check: {e}")

async def evening_message():
    for user_id in PROACTIVE_USERS:
        try:
            msg = generate_proactive_message(user_id, "evening")
            async with client.action(user_id, "typing"):
                await asyncio.sleep(random.uniform(3, 7))
            await send_message_smart(user_id, msg)
            last_proactive[user_id] = datetime.now(TZ)
        except Exception as e:
            print(f"Evening: {e}")

async def evening_budget_summary():
    for user_id in PROACTIVE_USERS:
        try:
            summary = get_daily_budget_summary(user_id)
            if summary:
                await send_message_smart(user_id, summary)
        except Exception as e:
            print(f"Budget summary error: {e}")

async def random_fact_message():
    for user_id in PROACTIVE_USERS:
        try:
            await client.send_message(user_id, random.choice(FACTS + QUOTES))
        except Exception as e:
            print(f"Fact message error for {user_id}: {e}")

async def daily_diary():
    for user_id in PROACTIVE_USERS:
        try:
            await write_diary_entry(user_id)
        except Exception as e:
            print(f"Daily diary error for {user_id}: {e}")

async def cleanup_followups():
    for user_id in PROACTIVE_USERS:
        try:
            clear_old_followups(user_id)
        except Exception as e:
            print(f"Cleanup followups error for {user_id}: {e}")

# ── Обработчик редактирований ─────────────────────────────────────────────────

@client.on(events.MessageEdited(func=lambda e: e.is_private))
async def edit_handler(event):
    user_id = event.sender_id
    sender  = await event.get_sender()
    if getattr(sender, "bot", False):
        return

    new_text = event.message.text
    if not new_text:
        return

    msg_id    = event.message.id
    user_msgs = last_messages.get(user_id, {})
    old_entry = user_msgs.get(str(msg_id))

    if not old_entry:
        return

    old_text = old_entry.get("text", "")
    if old_text == new_text:
        return

    edit_time = datetime.now(TZ)
    sent_time = old_entry.get("time")
    if sent_time:
        if (edit_time - sent_time).total_seconds() > 120:
            return

    print(f"✏️ Правка от {user_id}: '{old_text[:30]}' → '{new_text[:30]}'")

    if random.random() > 0.6:
        return

    edit_reactions = [
        "заметила что исправил 👀",
        "о, переписал? 😄",
        "ага, видела первый вариант",
        "исправился? интересно",
        "хм, передумал что-ли",
    ]

    if random.random() > 0.5:
        async with client.action(event.chat_id, "typing"):
            await asyncio.sleep(random.uniform(2, 4))
            new_reply = await get_reply(user_id, new_text)
        await send_message_smart(
            event.chat_id,
            f"{random.choice(edit_reactions)} — {new_reply}",
            user_message=new_text
        )
    else:
        async with client.action(event.chat_id, "typing"):
            await asyncio.sleep(random.uniform(1, 2.5))
        await client.send_message(event.chat_id, random.choice(edit_reactions))

    user_msgs[str(msg_id)]["text"] = new_text
    last_messages[user_id] = user_msgs

# ── Обработчик сообщений ──────────────────────────────────────────────────────

@client.on(events.NewMessage(func=lambda e: e.is_private))
async def handler(event):
    user_id = event.sender_id
    print(f"DEBUG: получено от {user_id}: {event.message.text[:30] if event.message.text else 'нет текста'}")
    sender = await event.get_sender()

    if getattr(sender, "bot", False):
        return

    last_user_message[user_id] = datetime.now(TZ)
    record_activity(user_id)

    # ── Голосовые входящие ────────────────────────────────────────────────────
    if event.message.voice:
        async with client.action(event.chat_id, "typing"):
            await asyncio.sleep(random.uniform(1.5, 3.0))
        await event.reply(random.choice([
            "голосовые пока не слышу 🙈 напиши текстом?",
            "не могу слушать голосовые, напиши 😊",
            "текстом пиши, дарлинг 😄",
        ]))
        return

    # ── Стикеры ───────────────────────────────────────────────────────────────
    if event.message.sticker:
        async with client.action(event.chat_id, "typing"):
            await asyncio.sleep(1.5)
        await event.reply(random.choice(["😄", "❤️", "🔥", "😂", "хе-хе 👀"]))
        return

    # ── Входящие фото ─────────────────────────────────────────────────────────
    if event.message.photo:
        async with client.action(event.chat_id, "typing"):
            await asyncio.sleep(random.uniform(1.5, 3.0))
        await event.reply(random.choice(PHOTO_RECEIVED_PHRASES))
        return

    text = event.message.text
    if not text:
        return

    # ── Сохраняем для отслеживания правок ────────────────────────────────────
    msg_id = event.message.id
    if user_id not in last_messages:
        last_messages[user_id] = {}
    user_msgs = last_messages[user_id]
    user_msgs[str(msg_id)] = {"text": text, "time": datetime.now(TZ)}
    if len(user_msgs) > 20:
        oldest = sorted(user_msgs.keys())[0]
        del user_msgs[oldest]
    last_messages[user_id] = user_msgs

    update_stats(user_id, getattr(sender, "username", None))
    text_low = text.lower().strip()

    # ── Мини-игры ─────────────────────────────────────────────────────────────
    if detect_game_stop(text_low) and is_game_active(user_id):
        result = stop_game(user_id)
        await event.reply(result)
        return

    game_type = detect_game_start(text_low)
    if game_type:
        async with client.action(event.chat_id, "typing"):
            await asyncio.sleep(random.uniform(1.0, 2.0))
        result = start_game(user_id, game_type, text)
        await event.reply(result, parse_mode="md")
        return

    if is_game_active(user_id):
        game_response = handle_game_input(user_id, text)
        if game_response:
            async with client.action(event.chat_id, "typing"):
                await asyncio.sleep(random.uniform(0.5, 1.5))
            await event.reply(game_response, parse_mode="md")
            return

    # ── Режим обучения языка ──────────────────────────────────────────────────
    if is_lang_active(user_id):
        if text.lower() in ("стоп", "stop", "хватит", "выход", "exit"):
            await event.reply(lang_stop(user_id))
            return
        if text.lower() in ("следующее", "дальше", "next", "ещё"):
            await event.reply(lang_next_word(user_id))
            return
        if text.lower() in ("статистика", "прогресс", "stats"):
            await event.reply(lang_stats(user_id))
            return
        is_correct, reaction = lang_check_answer(user_id, text)
        if reaction:
            await event.reply(reaction, parse_mode="md")
            await asyncio.sleep(1.5)
            await event.reply(lang_next_word(user_id), parse_mode="md")
            return

    # ── Быстрые команды ───────────────────────────────────────────────────────
    if any(t in text_low for t in ["который час", "сколько времени", "какое время", "что за время"]):
        await event.reply(get_current_time())
        return

    if any(t in text_low for t in ["запусти секундомер", "старт секундомер", "начни секундомер"]):
        await event.reply(stopwatch_start(user_id))
        return

    if any(t in text_low for t in ["останови секундомер", "стоп секундомер", "секундомер стоп"]):
        await event.reply(stopwatch_stop(user_id))
        return

    if any(t in text_low for t in ["сколько секундомер", "время секундомер", "секундомер сколько"]):
        await event.reply(stopwatch_status(user_id))
        return

    if any(t in text_low for t in ["расходы сегодня", "сколько потратил сегодня", "трата сегодня"]):
        await event.reply(get_expenses_today(user_id))
        return

    if any(t in text_low for t in ["расходы за месяц", "сколько потратил за месяц", "месячные расходы"]):
        await event.reply(get_expenses_month(user_id))
        return

    expense_match = re.search(
        r'(?:потратил|трата|заплатил|купил|купила)\s+(\d[\d\s]*(?:к|тыс)?)\s*(?:на\s+)?(.+)',
        text_low
    )
    if expense_match:
        raw_amount  = expense_match.group(1).replace(" ", "")
        description = expense_match.group(2).strip()
        amount      = float(raw_amount.replace("к", "000").replace("тыс", "000"))
        await event.reply(add_expense(user_id, amount, description))
        return

    lang_triggers = [
        "учи меня английскому", "давай учить английский",
        "режим препода", "учи слова", "учи меня словам",
        "начнём учиться", "учим английский",
    ]
    if any(t in text_low for t in lang_triggers):
        await event.reply(lang_start(user_id, "english"), parse_mode="md")
        return

    # ── Проверка памяти ───────────────────────────────────────────────────────
    memory_triggers = ["проверь память", "что помнишь", "что ты знаешь обо мне",
                       "расскажи что знаешь", "твоя память", "что помнишь обо мне"]
    if any(t in text_low for t in memory_triggers):
        mem = get_user_memory(user_id)
        history = load_history(user_id)

        lines = ["🧠 вот что я помню о тебе:\n"]

        if mem.get("name"):       lines.append(f"👤 имя: {mem['name']}")
        if mem.get("age"):        lines.append(f"🎂 возраст: {mem['age']}")
        if mem.get("city"):       lines.append(f"📍 город: {mem['city']}")
        if mem.get("birthday"):   lines.append(f"🎉 день рождения: {mem['birthday']}")
        if mem.get("interests"):  lines.append(f"💡 интересы: {', '.join(mem['interests'][:5])}")
        if mem.get("goals"):      lines.append(f"🎯 цели: {', '.join(mem['goals'][:3])}")
        if mem.get("last_topic"): lines.append(f"💬 последняя тема: {mem['last_topic']}")
        if mem.get("likes"):      lines.append(f"❤️ нравится: {', '.join(mem['likes'][:3])}")
        if mem.get("dislikes"):   lines.append(f"😤 не нравится: {', '.join(mem['dislikes'][:3])}")

        rel   = mem.get("relationship_level", 0)
        count = mem.get("message_count", 0)
        lines.append(f"\n📊 сообщений: {count} | близость: {rel}/100")
        lines.append(f"💾 диалогов в памяти: {len(history)}")

        if len(lines) <= 3:
            await event.reply("пока почти ничего не знаю о тебе 🙈 расскажи что-нибудь")
        else:
            await event.reply("\n".join(lines))
        return

    # ── Генерация изображений ─────────────────────────────────────────────────
    image_prompt = is_image_request(text)
    if image_prompt:
        await event.reply(random.choice(GENERATION_PHRASES))
        async with client.action(event.chat_id, "document"):
            image_path = await generate_image(image_prompt)
        if image_path:
            try:
                await client.send_file(
                    event.chat_id, image_path,
                    caption=random.choice(["вот 🎨", "держи ✨", "нарисовала 🖼", ""]),
                )
                os.unlink(image_path)
            except Exception as e:
                print(f"Image send error: {e}")
                await client.send_message(event.chat_id, random.choice(GENERATION_FAIL_PHRASES))
        else:
            await client.send_message(event.chat_id, random.choice(GENERATION_FAIL_PHRASES))
        return

    # ── Админ-команды ─────────────────────────────────────────────────────────
    if user_id == ADMIN_ID:
        if text.startswith("/stats"):
            await event.reply(get_stats_text(), parse_mode="HTML")
            return
        if text.startswith("/set_mood "):
            user_moods[user_id] = text.replace("/set_mood ", "").strip()
            await event.reply(f"✅ Настроение: {user_moods[user_id]}")
            return
        if text.startswith("/clear_tasks"):
            target = int(text.split()[-1]) if len(text.split()) > 1 else user_id
            clear_user_tasks(target)
            await event.reply("✅ Задачи очищены")
            return
        if text.startswith("/memory"):
            target = int(text.split()[-1]) if len(text.split()) > 1 else user_id
            mem    = get_user_memory(target)
            await event.reply(f"<pre>{json.dumps(mem, ensure_ascii=False, indent=2)}</pre>", parse_mode="HTML")
            return
        if text.startswith("/goals"):
            target = int(text.split()[-1]) if len(text.split()) > 1 else user_id
            mem    = get_user_memory(target)
            goals  = mem.get("goals") or []
            await event.reply(f"🎯 Цели: {', '.join(goals) if goals else 'нет'}")
            return
        if text.startswith("/diary"):
            target = int(text.split()[-1]) if len(text.split()) > 1 else user_id
            await event.reply(get_diary_stats(target))
            return
        if text.startswith("/patterns"):
            target = int(text.split()[-1]) if len(text.split()) > 1 else user_id
            await event.reply(get_predictor_stats(target))
            return
        if text.startswith("/broadcast "):
            msg   = text.replace("/broadcast ", "").strip()
            stats = load_json(STATS_FILE)
            count = 0
            for uid in stats:
                try:
                    await client.send_message(int(uid), msg)
                    count += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"Broadcast error for {uid}: {e}")
            await event.reply(f"✅ Отправлено {count} пользователям")
            return
        if text.startswith("/summarize"):
            await summarize_all()
            await event.reply("✅ Резюме сохранено для всех")
            return
        if text.startswith("/mode"):
            parts = text.split()
            if len(parts) > 1:
                user_18plus_mode[user_id] = parts[1].strip()
                await event.reply(f"✅ Режим: {parts[1].strip()}")
            return
        if text.startswith("/poke"):
            target = int(text.split()[-1]) if len(text.split()) > 1 else user_id
            msg    = generate_proactive_message(target, "random")
            await client.send_message(target, msg)
            await event.reply(f"✅ Отправлено: {msg}")
            return
        if text.startswith("/stopgame"):
            target = int(text.split()[-1]) if len(text.split()) > 1 else user_id
            result = stop_game(target) if is_game_active(target) else "игры нет"
            await event.reply(f"✅ {result}")
            return

    # ── Запрос голосового ─────────────────────────────────────────────────────
    voice_triggers = ["голосовое", "голосом", "запиши", "скажи голосом", "ovozli", "voice"]
    if any(t in text_low for t in voice_triggers):
        voice_requested[user_id] = True

    # ── Иногда "читает но не отвечает" сразу ─────────────────────────────────
    hour = datetime.now(TZ).hour
    if 9 <= hour <= 23 and random.random() < 0.15:
        read_delay = random.uniform(20, 90)
        print(f"👁 {user_id}: читает, пауза {read_delay:.0f}с")
        await asyncio.sleep(read_delay)

    # ── Генерируем ответ ──────────────────────────────────────────────────────
    async with client.action(event.chat_id, "typing"):
        raw_reply = await get_reply(user_id, text)
        delay     = calc_typing_delay(raw_reply)
        await asyncio.sleep(delay)

    reply, extras = detect_tool_calls(raw_reply, user_id)

    if reply:
        await send_message_smart(event.chat_id, reply, reply_to=event, user_message=text)

    # ── Голосовое — только если явно попросили ────────────────────────────────
    force_voice = voice_requested.pop(user_id, False)
    if force_voice and reply:
        voice_path = await text_to_voice(reply, bot_mood=get_current_mood(user_id))
        if voice_path:
            try:
                await client.send_file(
                    event.chat_id, voice_path, voice_note=True,
                    attributes=[DocumentAttributeAudio(duration=0, voice=True)]
                )
            except Exception as e:
                print(f"Voice send: {e}")
            finally:
                try: os.unlink(voice_path)
                except: pass

    # ── Follow-up вопросы ─────────────────────────────────────────────────────
    pending = get_pending_followups(user_id)
    for question in pending:
        await asyncio.sleep(1.5)
        await send_message_smart(event.chat_id, question)

    # ── Tool-calling результаты ───────────────────────────────────────────────
    for kind, content in extras:
        if kind == "text":
            await asyncio.sleep(0.5)
            await client.send_message(event.chat_id, content)
        elif kind == "generate_image":
            async with client.action(event.chat_id, "document"):
                image_path = await generate_image(content)
            if image_path:
                try:
                    await client.send_file(event.chat_id, image_path, caption="🎨")
                    os.unlink(image_path)
                except Exception as e:
                    print(f"Tool image send error: {e}")
            else:
                await client.send_message(event.chat_id, random.choice(GENERATION_FAIL_PHRASES))

# ── Запуск ────────────────────────────────────────────────────────────────────

async def main():
    print("📥 Загружаю данные из GitHub...")
    for filename in [MEMORY_FILE, TASKS_FILE, STATS_FILE, HISTORY_FILE, STYLE_FILE]:
        data = github_download(filename)
        if data is not None:
            save_json_local(filename, data)
            print(f"✅ Загружен: {filename} ({len(data)} записей)")
        else:
            print(f"⚠️ Не загружен: {filename}")

    await client.start()
    me = await client.get_me()
    print(f"✅ Бот запущен: @{me.username}")
    print(f"🤖 Groq: {len(GROQ_KEYS)} ключей | Gemini резерв")
    print(f"🎙 edge-tts | gTTS резерв")
    print(f"🎮 Игры: города, угадай число, виселица, матспринт, крестики-нолики")
    print(f"🕐 UTC+5 | 👤 Админ: {ADMIN_ID}")

    # Прогреваем entity кэш для всех юзеров из задач
    print("🔄 Прогрев entity кэша...")
    tasks = load_tasks()
    warmed = set()
    for task in tasks:
        uid = task.get("user_id")
        if uid and uid not in warmed:
            try:
                await client.get_input_entity(uid)
                warmed.add(uid)
            except Exception:
                pass
    for uid in PROACTIVE_USERS:
        if uid not in warmed:
            try:
                await client.get_input_entity(uid)
                warmed.add(uid)
            except Exception:
                pass
    if warmed:
        print(f"✅ Entity кэш прогрет для {len(warmed)} пользователей")

    scheduler.add_job(flush_uploads,          "interval", minutes=5)
    scheduler.add_job(proactive_message,      "interval", minutes=90)

    # ── Жёсткое расписание дня (Шифу) ────────────────────────────────────────
    scheduler.add_job(wake_up_call,           "cron", hour=5,  minute=0)
    scheduler.add_job(run_reminder,           "cron", hour=5,  minute=15)
    scheduler.add_job(prayer_reminder,        "cron", hour=6,  minute=0)
    scheduler.add_job(schedule_plan_reminder, "cron", hour=6,  minute=15)
    scheduler.add_job(breakfast_reminder,     "cron", hour=6,  minute=30)
    scheduler.add_job(lunch_reminder,         "cron", hour=13, minute=0)
    scheduler.add_job(evening_training_reminder, "cron", hour=18, minute=0)
    scheduler.add_job(sleep_reminder,         "cron", hour=22, minute=0)
    scheduler.add_job(late_night_check,       "interval", minutes=30)

    scheduler.add_job(morning_message,        "cron",     hour=9,  minute=30)
    scheduler.add_job(evening_message,        "cron",     hour=20, minute=0)
    scheduler.add_job(evening_budget_summary, "cron",     hour=21, minute=30)
    scheduler.add_job(check_tasks,            "interval", minutes=1)
    scheduler.add_job(check_birthdays,        "cron",     hour=9,  minute=0)
    scheduler.add_job(autosave_to_github,     "interval", hours=2)
    scheduler.add_job(random_fact_message,    "interval", hours=72)
    scheduler.add_job(summarize_all,          "cron",     hour=23, minute=30)
    scheduler.add_job(daily_diary,            "cron",     hour=23, minute=0)
    scheduler.add_job(cleanup_followups,      "cron",     hour=3,  minute=0)
    scheduler.start()

    print("⚡ Жду сообщений... (Ctrl+C для остановки)")
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
