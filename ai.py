import asyncio, json, re, random
from datetime import datetime
from config import (
    TZ, GROQ_MODELS, groq_cycle, groq_pool, gemini_client, openrouter_client,
)
from memory import (
    get_user_memory, update_user_memory, increment_relationship,
    get_relationship_style, load_history, save_history,
    load_user_style, save_user_style,
)
from personality import (
    SYSTEM_PROMPT, get_mood, message_counters,
    detect_emotion, get_emotion_response, get_emotion_context,
    build_style_context, build_memory_context
)
from tools import (
    add_expense,
    get_weather,
    get_exchange_rate,
    search_wikipedia,
    get_news,
    add_task,
    add_daily_task,
    remove_daily_task,
    get_daily_tasks,
    needs_wiki,   
    needs_news,   
)

from finance import add_expense, add_income, get_report, get_balance, delete_last
from finance_parser import detect_finance_command

from mood_tracker import (
    process_message, get_mood_context,
    get_mood_reaction, get_current_mood
)
from followup_tracker import (
    check_and_add_followup, get_pending_followups, clear_old_followups
)
from diary import (
    get_diary_context, needs_diary_entry,
    build_diary_prompt, add_diary_entry
)
from mood_predictor import (
    get_prediction_context, record_from_emotion
)
from news_reaction import (
    should_react_to_news, get_news_with_cache,
    build_news_opinion_prompt, get_quick_reaction
)

# ── Состояние ─────────────────────────────────────────────────────────────────

conversations:   dict = {}
last_proactive:  dict = {}
voice_requested: dict = {}

# Заглушки для обратной совместимости с main.py (18+ режим убран)
user_18plus_mode:    dict = {}
user_18plus_counter: dict = {}
user_history_normal: dict = {}

# ── Groq + Gemini ─────────────────────────────────────────────────────────────

_last_working_key_index = 0

def get_ai_reply_sync(
    messages: list,
    system: str = "",
    temperature: float = 0.9,
    max_tokens: int = 150,
    skip_gemini: bool = False
) -> str:
    global _last_working_key_index
    msgs = ([{"role": "system", "content": system}] if system else []) + messages

    for attempt in range(len(groq_pool)):
        idx = (_last_working_key_index + attempt) % len(groq_pool)
        client_groq = groq_pool[idx]
        hit_rate_limit = False
        for model in GROQ_MODELS:
            try:
                r = client_groq.chat.completions.create(
                    model=model,
                    messages=msgs,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                _last_working_key_index = idx
                return r.choices[0].message.content.strip()
            except Exception as e:
                err = str(e)
                if "429" in err:
                    print(f"⚠️ Groq ключ #{idx+1} лимит, пробую следующий...")
                    hit_rate_limit = True
                    break
                else:
                    print(f"⚠️ Groq ключ #{idx+1} ({model}): {e}")
                    continue
        if not hit_rate_limit:
            break

    print("⏳ Все Groq ключи на лимите, жду 3с и пробую ещё раз...")
    import time
    time.sleep(3)
    for idx in range(len(groq_pool)):
        try:
            r = groq_pool[idx].chat.completions.create(
                model=GROQ_MODELS[0],
                messages=msgs,
                max_tokens=min(max_tokens, 150),
                temperature=temperature,
            )
            _last_working_key_index = idx
            print(f"✅ Groq ключ #{idx+1} ожил после паузы")
            return r.choices[0].message.content.strip()
        except Exception:
            continue

    print("🔄 Переключаюсь на Gemini")

    if skip_gemini:
        return "потом"

    try:
        recent = messages[-10:]
        gemini_system = (system if system else "") + """

ВАЖНО: Ты отвечаешь КАК Камилла — холодный злодей в женском роде.
Отвечай коротко, резко, без эмодзи. Только текст ответа.
"""
        prompt = gemini_system + "\n\n" + "\n".join(
            f"{'Пользователь' if m['role'] == 'user' else 'Камилла'}: {m['content']}"
            for m in recent
            if m['role'] in ('user', 'assistant')
        ) + "\nКамилла:"

        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt
        )
        text = response.text.strip() if response.text else ""
        if text:
            return text
    except Exception as e:
        print(f"⚠️ Gemini: {e}")

    if openrouter_client:
        try:
            r = openrouter_client.chat.completions.create(
                model="meta-llama/llama-3.3-70b-instruct:free",
                messages=msgs,
                max_tokens=150,
            )
            text = r.choices[0].message.content.strip()
            if text:
                print("✅ OpenRouter ответил")
                return text
        except Exception as e:
            print(f"⚠️ OpenRouter: {e}")

    return "потом"


# ── Tool-calling ──────────────────────────────────────────────────────────────

TOOLS_DESCRIPTION = """
Ты можешь вызывать инструменты если пользователь явно намекает на них.
Вставь команду ПЕРЕД текстом ответа. Можно вставить несколько команд подряд,
если пользователь просит несколько задач за один раз.
 
[TOOL:expense|сумма|описание] — записать расход
  Когда: "потратил 50к на еду", "купил за 200000"
  Пример: [TOOL:expense|50000|еда]
 
[TOOL:task|минуты|описание] — РАЗОВОЕ напоминание через N минут от сейчас
  Когда: "напомни через час", "не дай забыть про встречу через 30 минут"
  Пример: [TOOL:task|60|встреча]
 
[TOOL:daily|время|описание] — ЕЖЕДНЕВНАЯ повторяющаяся задача на фиксированное время
  Когда: "запомни задачи на утро/обед/вечер", "каждый день напоминай мне про Х в 9 утра",
         "напоминай завтракать", "вечером напоминай про растяжку"
  Время указывай в формате ЧЧ:ММ (24-часовой формат).
  Если пользователь не называет точное время, а говорит "утром"/"днём"/"вечером" —
  переводи сама: утро → 09:00, обед → 13:00, вечер → 19:00 (если по контексту не понятно иначе).
  Если в одном сообщении несколько задач на разное время дня — вставляй несколько
  [TOOL:daily|...] команд подряд, одну на каждую задачу.
  Примеры:
    [TOOL:daily|09:00|выпить воды и позавтракать]
    [TOOL:daily|13:00|сделать перерыв на обед]
    [TOOL:daily|19:00|растяжка и итоги дня]
 
[TOOL:remove_daily|описание] — убрать ежедневную задачу
  Когда: "не напоминай больше про Х", "убери задачу на вечер про Х"
  Пример: [TOOL:remove_daily|растяжка]
 
[TOOL:weather|город] — узнать погоду
  Когда: "какая погода", "что на улице"
  Пример: [TOOL:weather|Ташкент]
 
[TOOL:rate|валюта] — курс валюты
  Когда: "сколько стоит доллар", "курс евро"
  Пример: [TOOL:rate|USD]
 
[TOOL:wiki|запрос] — найти информацию
  Когда: "кто такой", "что такое"
  Пример: [TOOL:wiki|Илон Маск]
 
[TOOL:image|промпт] — нарисовать картинку
  Пример: [TOOL:image|dark warrior]
 
[TOOL:game|тип] — предложить мини-игру
  Типы: cities, number, hangman, mathsprint, tictactoe
  Пример: [TOOL:game|number]
 
Правила:
- Команда(ы) идут перед текстом ответа
- Используй только когда реально нужно
- Если пользователь явно просит "запомни" задачу с привязкой ко времени дня —
  ОБЯЗАТЕЛЬНО используй [TOOL:daily|...], а не просто слова "хорошо, запомню"
"""

def detect_tool_calls(text: str, user_id: int) -> tuple[str, list]:
    from tools import add_expense, get_weather, get_exchange_rate, search_wikipedia, get_news, add_task
    from games import start_game, is_game_active

    actions = []
    clean   = text

    # Ежедневные задачи
    for m in re.finditer(r'\[TOOL:daily\|([0-9:]+)\|(.+?)\]', text):
        time_str = m.group(1).strip()
        desc     = m.group(2).strip()
        normalized = add_daily_task(user_id, desc, time_str)
        if normalized:
            actions.append(("text", f"📌 запомнила: «{desc}» каждый день в {normalized}"))
        else:
            actions.append(("text", f"не поняла время для «{desc}», уточни формат ЧЧ:ММ"))
        clean = clean.replace(m.group(0), "").strip()

    # Удаление ежедневной задачи
    for m in re.finditer(r'\[TOOL:remove_daily\|(.+?)\]', text):
        desc    = m.group(1).strip()
        removed = remove_daily_task(user_id, desc)
        if removed:
            actions.append(("text", f"убрала задачу: «{desc}»"))
        else:
            actions.append(("text", f"не нашла такую задачу: «{desc}»"))
        clean = clean.replace(m.group(0), "").strip()

    # Расходы
    for m in re.finditer(r'\[TOOL:expense\|(\d+(?:\.\d+)?)\|(.+?)\]', text):
        amount      = float(m.group(1))
        description = m.group(2).strip()
        result      = add_expense(user_id, amount, description)
        actions.append(("text", result))
        clean = clean.replace(m.group(0), "").strip()

    # Разовые напоминания
    for m in re.finditer(r'\[TOOL:task\|(\d+)\|(.+?)\]', text):
        minutes = int(m.group(1))
        desc    = m.group(2).strip()
        add_task(user_id, desc, minutes)
        actions.append(("text", f"⏰ напомню: {desc}"))
        clean = clean.replace(m.group(0), "").strip()

    # Погода
    for m in re.finditer(r'\[TOOL:weather\|(.+?)\]', text):
        city   = m.group(1).strip()
        result = get_weather(city)
        actions.append(("text", result))
        clean = clean.replace(m.group(0), "").strip()

    # Курс валюты
    for m in re.finditer(r'\[TOOL:rate\|(.+?)\]', text):
        currency = m.group(1).strip()
        result   = get_exchange_rate(currency)
        actions.append(("text", result))
        clean = clean.replace(m.group(0), "").strip()

    # Wikipedia
    for m in re.finditer(r'\[TOOL:wiki\|(.+?)\]', text):
        query  = m.group(1).strip()
        result = search_wikipedia(query)
        if result:
            actions.append(("text", result))
        clean = clean.replace(m.group(0), "").strip()

    # Генерация изображения
    for m in re.finditer(r'\[TOOL:image\|(.+?)\]', text):
        prompt = m.group(1).strip()
        actions.append(("generate_image", prompt))
        clean = clean.replace(m.group(0), "").strip()

    # Игры
    for m in re.finditer(r'\[TOOL:game\|(.+?)\]', text):
        game_type   = m.group(1).strip()
        valid_types = {"cities", "number", "hangman", "mathsprint", "tictactoe"}
        if game_type in valid_types and not is_game_active(user_id):
            result = start_game(user_id, game_type)
            actions.append(("text", result))
        clean = clean.replace(m.group(0), "").strip()

    return clean.strip(), actions


# ── Личный дневник (облегчённый — только запись тем) ─────────────────────────

async def write_diary_entry(user_id: int):
    if not needs_diary_entry(user_id):
        return

    history = conversations.get(user_id, [])
    if len(history) < 4:
        return

    mem    = get_user_memory(user_id)
    prompt = build_diary_prompt(user_id, history, user_name=mem.get("name"))

    try:
        reply = get_ai_reply_sync(
            [{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=120
        )
        clean = re.sub(r'```json|```', '', reply).strip()
        data  = json.loads(clean)
        entry = data.get("entry", "").strip()
        mood  = data.get("mood", "neutral")
        if entry:
            add_diary_entry(user_id, entry, mood)
    except Exception as e:
        print(f"⚠️ Дневник: {e}")


# ── Обучение на чатах ─────────────────────────────────────────────────────────

async def learn_from_history(user_id: int):
    history = load_history(user_id)
    if len(history) < 20:
        return
    user_msgs = [m["content"] for m in history if m["role"] == "user"][-30:]
    prompt = (
        "Проанализируй сообщения пользователя и верни ТОЛЬКО JSON без лишнего текста.\n"
        '{"preferred_topics": [], "response_style": "", '
        '"common_phrases": [], "avg_message_length": 0, '
        '"conversation_patterns": [], "humor_level": ""}\n'
        f"Сообщения: {json.dumps(user_msgs, ensure_ascii=False)}"
    )
    try:
        reply = get_ai_reply_sync([{"role": "user", "content": prompt}], max_tokens=300)
        clean = re.sub(r'```json|```', '', reply).strip()
        data  = json.loads(clean)
        save_user_style(user_id, data)
        print(f"🧠 Стиль обновлён для {user_id}")
    except Exception as e:
        print(f"Ошибка обучения: {e}")


# ── Анализ профиля ────────────────────────────────────────────────────────────

async def analyze_and_update_profile(user_id: int, messages: list):
    if len(messages) < 4:
        return
    user_msgs = [m["content"] for m in messages if m["role"] == "user"][-10:]
    if not user_msgs:
        return
    fmt = ('{"name":null,"age":null,"city":null,"birthday":null,"interests":[],'
           '"communication_style":null,"frequent_topics":[],"likes":[],'
           '"dislikes":[],"important_events":[],"notes":[],"goals":[]}')
    prompt = (
        "Проанализируй сообщения и верни ТОЛЬКО JSON без лишнего текста.\n"
        "В поле goals записывай цели/намерения пользователя.\n"
        f"Сообщения: {json.dumps(user_msgs, ensure_ascii=False)}\n"
        f"Формат: {fmt}"
    )
    try:
        reply    = get_ai_reply_sync([{"role": "user", "content": prompt}], max_tokens=300)
        clean    = re.sub(r'```json|```', '', reply).strip()
        data     = json.loads(clean)
        existing = get_user_memory(user_id)
        for key, val in data.items():
            if val:
                if isinstance(val, list):
                    existing[key] = list(set((existing.get(key) or []) + val))[:10]
                else:
                    existing[key] = val
        update_user_memory(user_id, existing)
        print(f"🧠 Профиль обновлён: {user_id}")
    except Exception as e:
        print(f"Ошибка анализа: {e}")


# ── Резюме разговора ──────────────────────────────────────────────────────────

async def summarize_conversation(user_id: int):
    history = conversations.get(user_id, [])
    if len(history) < 4:
        return
    user_msgs = [m["content"] for m in history if m["role"] == "user"][-15:]
    prompt = (
        "Коротко резюмируй о чём говорил пользователь сегодня. "
        "Ответ ТОЛЬКО JSON:\n"
        '{"main_topic": "...", "unfinished": null, "goals_mentioned": []}\n'
        f"Сообщения: {json.dumps(user_msgs, ensure_ascii=False)}"
    )
    try:
        reply = get_ai_reply_sync([{"role": "user", "content": prompt}], max_tokens=300)
        clean = re.sub(r'```json|```', '', reply).strip()
        data  = json.loads(clean)
        today = datetime.now(TZ).strftime("%d.%m.%Y")
        mem   = get_user_memory(user_id)

        mem["last_topic"]                = data.get("main_topic")
        mem["unfinished"]                = data.get("unfinished")
        mem["last_conversation_date"]    = today
        mem["last_conversation_summary"] = data.get("main_topic")

        if data.get("goals_mentioned"):
            existing_goals = mem.get("goals") or []
            for g in data["goals_mentioned"]:
                if g and g not in existing_goals:
                    existing_goals.append(g)
            mem["goals"] = existing_goals[-10:]

        update_user_memory(user_id, mem)
        print(f"📝 Резюме для {user_id}: {data.get('main_topic')}")
    except Exception as e:
        print(f"Ошибка резюме: {e}")


async def summarize_all():
    for user_id in list(conversations.keys()):
        await summarize_conversation(user_id)


# ── Главная функция ответа ────────────────────────────────────────────────────

async def get_reply(user_id: int, user_message: str) -> str:
    # ── Инициализация истории ──
    if user_id not in conversations:
        conversations[user_id] = load_history(user_id)

    history = conversations.setdefault(user_id, [])

    counter = message_counters.get(user_id, 0) + 1
    message_counters[user_id] = counter

    mood     = get_mood(user_id)
    user_mem = get_user_memory(user_id)
    level    = increment_relationship(user_id)
    today    = datetime.now(TZ).strftime("%d.%m.%Y")

    # ── Настроение бота (mood_tracker) ──
    mood_event    = process_message(user_id, user_message)
    mood_reaction = None
    if mood_event:
        mood_reaction = get_mood_reaction(mood_event)
    mood_ctx = get_mood_context(user_id)

    if mood_reaction:
        history.append({"role": "user",     "content": user_message})
        history.append({"role": "assistant", "content": mood_reaction})
        save_history(user_id, history)
        return mood_reaction

    # ── Финансовые команды (обрабатываем до AI) ──
    fin = detect_finance_command(user_message)
    if fin:
        cmd = fin["cmd"]
        if cmd == "expense":
            result = add_expense(user_id, fin["amount"], fin.get("description", ""))
            history.append({"role": "user",      "content": user_message})
            history.append({"role": "assistant",  "content": result})
            save_history(user_id, history)
            return result
        elif cmd == "income":
            result = add_income(user_id, fin["amount"], fin.get("description", ""))
            history.append({"role": "user",      "content": user_message})
            history.append({"role": "assistant",  "content": result})
            save_history(user_id, history)
            return result
        elif cmd == "report":
            result = get_report(user_id, fin.get("period", "month"))
            history.append({"role": "user",      "content": user_message})
            history.append({"role": "assistant",  "content": result})
            save_history(user_id, history)
            return result
        elif cmd == "balance":
            result = get_balance(user_id)
            history.append({"role": "user",      "content": user_message})
            history.append({"role": "assistant",  "content": result})
            save_history(user_id, history)
            return result
        elif cmd == "delete_last":
            result = delete_last(user_id)
            history.append({"role": "user",      "content": user_message})
            history.append({"role": "assistant",  "content": result})
            save_history(user_id, history)
            return result

    # ── Follow-up отслеживание ──
    check_and_add_followup(user_id, user_message)

    # ── Эмоция пользователя ──
    emotion     = detect_emotion(user_message)
    emotion_ctx = ""

    if emotion:
        update_user_memory(user_id, {"current_emotion": emotion})
        record_from_emotion(user_id, emotion)

        if random.random() > 0.6:
            ready = get_emotion_response(emotion)
            if ready:
                history.append({"role": "user",     "content": user_message})
                history.append({"role": "assistant", "content": ready})
                save_history(user_id, history)
                return ready

        emotion_ctx = f"\n\nЭМОЦИЯ ПОЛЬЗОВАТЕЛЯ: {emotion}. {get_emotion_context(emotion)}"

    # ── Контекст памяти ──
    memory_ctx = build_memory_context(user_mem, level, today)
    continuation_ctx = ""
    days_str = ""

    # ── Личный дневник ──
    diary_ctx = get_diary_context(user_id)

    # ── Предсказание настроения ──
    prediction_ctx = get_prediction_context(user_id)

    # ── Стиль пользователя ──
    user_style = load_user_style(user_id)
    style_ctx  = build_style_context(user_style)

    # ── Wikipedia автопоиск ──
    wiki_ctx   = ""
    wiki_query = needs_wiki(user_message)
    if wiki_query:
        result = search_wikipedia(wiki_query)
        if result:
            wiki_ctx = f"\n\nСПРАВКА: {result}"

    # ── Новости автопоиск ──
    news_ctx   = ""
    news_topic = needs_news(user_message)
    if news_topic:
        news = get_news(news_topic)
        if news:
            news_ctx = f"\n\nНОВОСТИ по теме '{news_topic}': " + " | ".join(news)

    # ── Живая реакция на новости ──
    news_opinion_ctx = ""
    reaction_topic   = should_react_to_news(user_message)
    if reaction_topic and not news_topic:
        articles = get_news_with_cache(reaction_topic)
        if articles:
            opinion_prompt = build_news_opinion_prompt(reaction_topic, articles, user_message)
            try:
                opinion = get_ai_reply_sync(
                    [{"role": "user", "content": opinion_prompt}],
                    temperature=0.95,
                    max_tokens=150
                )
                news_opinion_ctx = f"\n\nМНЕНИЕ О НОВОСТИ: {opinion}"
            except Exception:
                news_opinion_ctx = f"\n\nРЕАКЦИЯ: {get_quick_reaction(reaction_topic)}"
        else:
            news_opinion_ctx = f"\n\nРЕАКЦИЯ: {get_quick_reaction(reaction_topic)}"

    # ── Контекст активной игры ──
    from games import get_game
    game_ctx = ""
    active_game = get_game(user_id)
    if active_game:
        game_names = {
            "cities":     "города",
            "number":     "угадай число",
            "hangman":    "виселица",
            "mathsprint": "математический спринт",
            "tictactoe":  "крестики-нолики",
        }
        gname = game_names.get(active_game["type"], active_game["type"])
        game_ctx = f"\n\nСЕЙЧАС ИДЁТ ИГРА: {gname}. Не ломай игровой процесс."

    # ── Сборка system prompt ──
    system = (
        SYSTEM_PROMPT
        + f"\n\nНастроение: {mood}."
        + f"\n\nУровень отношений: {get_relationship_style(level)} ({level}/100)"
        + f"\n\nЧто знаю о нём: {memory_ctx}"
        + continuation_ctx
        + diary_ctx
        + prediction_ctx
        + style_ctx
        + emotion_ctx
        + mood_ctx
        + wiki_ctx
        + news_ctx
        + news_opinion_ctx
        + game_ctx
        + f"\n\n{TOOLS_DESCRIPTION}"
    )

    # ── Отправка в AI ──
    history.append({"role": "user", "content": user_message})

    if len(history) > 20:
        history = history[-20:]
        conversations[user_id] = history

    reply = get_ai_reply_sync(
        history,
        system=system,
        temperature=0.9,
        max_tokens=150,
    )
    history.append({"role": "assistant", "content": reply})

    save_history(user_id, history)

    # ── Фоновые задачи ──
    if counter % 100 == 0:
        asyncio.create_task(analyze_and_update_profile(user_id, history))

    if counter % 75 == 0:
        asyncio.create_task(write_diary_entry(user_id))

    if counter % 150 == 0:
        asyncio.create_task(learn_from_history(user_id))

    update_user_memory(user_id, {})
    return reply
