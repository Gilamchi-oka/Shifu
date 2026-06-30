import json, os, base64, requests
import asyncio
from datetime import datetime
from config import (
    TZ, MEMORY_FILE, TASKS_FILE, STATS_FILE,
    HISTORY_FILE, STYLE_FILE, FEELINGS_FILE,
    GITHUB_TOKEN, GITHUB_REPO
)
from activity_tracker import ACTIVITY_FILE

# ── GitHub ────────────────────────────────────────────────────────────────────

def github_download(filename):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print(f"❌ GitHub: токен или репо не заданы")
        return None
    try:
        url     = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        print(f"🔍 GitHub запрос: {url}")
        r = requests.get(url, headers=headers, timeout=10)
        r.encoding = "utf-8"  # ← вот этой строки не хватало
        print(f"🔍 GitHub статус: {r.status_code} для {filename}")
        if r.status_code == 200:
            raw     = r.json()
            content = raw.get("content", "")
            if not content:
                print(f"⚠️ GitHub: пустой content для {filename}")
                return None
            decoded = base64.b64decode(content).decode("utf-8").strip()
            return json.loads(decoded)
        elif r.status_code == 404:
            print(f"❌ GitHub 404: файл {filename} не найден в репо {GITHUB_REPO}")
        else:
            print(f"❌ GitHub ошибка {r.status_code} для {filename}")
    except Exception as e:
        print(f"❌ GitHub download exception: {e}")
    return None
    
# ── Батчинг загрузок на GitHub ────────────────────────────────────────────────

_pending_uploads: set = set()

def _schedule_upload(filename: str):
    """Помечает файл для загрузки на GitHub при следующем flush."""
    _pending_uploads.add(filename)

async def flush_uploads():
    """Вызывается по таймеру каждые 5 минут — загружает накопленные изменения."""
    for filename in list(_pending_uploads):
        if os.path.exists(filename):
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    data = json.load(f)
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, github_upload, filename, data)
                _pending_uploads.discard(filename)
            except Exception as e:
                print(f"flush_uploads error ({filename}): {e}")

def github_upload(filename, data):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print(f"❌ Upload: токен или репо не заданы")
        return
    try:
        url     = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
        headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}
        content = base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode()).decode()
        r       = requests.get(url, headers=headers, timeout=10)
        sha     = r.json().get("sha") if r.status_code == 200 else None
        payload = {"message": f"auto: update {filename}", "content": content}
        if sha:
            payload["sha"] = sha
        result = requests.put(url, headers=headers, json=payload, timeout=10)
        result.encoding = "utf-8"  # ← добавить
        print(f"✅ GitHub upload {filename}: статус {result.status_code}")
        if result.status_code not in (200, 201):
            print(f"❌ GitHub upload error: статус {result.status_code}")
    except Exception as e:
        print(f"❌ GitHub upload exception ({filename}): {str(e).encode('utf-8', errors='replace').decode()}")
# ── JSON утилиты ──────────────────────────────────────────────────────────────

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return {}
                return json.loads(content)
        except Exception as e:
            print(f"⚠️ load_json error ({path}): {e}")
            return {}
    data = github_download(path)
    if data is not None:
        save_json_local(path, data)
        return data
    return {}

def save_json_local(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_json(path, data):
    save_json_local(path, data)

async def autosave_to_github():
    for filename in [MEMORY_FILE, TASKS_FILE, STATS_FILE, HISTORY_FILE, STYLE_FILE, FEELINGS_FILE, ACTIVITY_FILE]:
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            github_upload(filename, data)

# ── История чатов ─────────────────────────────────────────────────────────────

def save_history(user_id: int, history: list):
    data = load_json(HISTORY_FILE)
    data[str(user_id)] = history[-50:]
    save_json(HISTORY_FILE, data)
    _schedule_upload(HISTORY_FILE)

def load_history(user_id: int) -> list:
    data = load_json(HISTORY_FILE)
    return data.get(str(user_id), [])

# ── Стиль общения по юзеру ────────────────────────────────────────────────────

def save_user_style(user_id: int, style_data: dict):
    data = load_json(STYLE_FILE)
    data[str(user_id)] = style_data
    save_json(STYLE_FILE, data)
    _schedule_upload(STYLE_FILE)

def load_user_style(user_id: int) -> dict:
    data = load_json(STYLE_FILE)
    return data.get(str(user_id), {})

# ── Дневник чувств ────────────────────────────────────────────────────────────

def load_feelings(user_id: int) -> dict:
    data = load_json(FEELINGS_FILE)
    return data.get(str(user_id), {
        "entries":        [],
        "overall_mood":   "нейтральное",
        "bond_level":     "незнакомец",
        "last_updated":   None,
        "positive_count": 0,
        "negative_count": 0,
    })

def save_feelings(user_id: int, data: dict):
    all_data = load_json(FEELINGS_FILE)
    all_data[str(user_id)] = data
    save_json(FEELINGS_FILE, all_data)
    _schedule_upload(FEELINGS_FILE)

def add_feeling_entry(user_id: int, entry_text: str, sentiment: str = "neutral"):
    feelings = load_feelings(user_id)
    now = datetime.now(TZ).strftime("%d.%m.%Y %H:%M")

    feelings["entries"].append({
        "date": now,
        "text": entry_text,
        "sentiment": sentiment
    })
    feelings["entries"] = feelings["entries"][-20:]
    feelings["last_updated"] = now

    if sentiment == "positive":
        feelings["positive_count"] += 1
    elif sentiment == "negative":
        feelings["negative_count"] += 1

    pos   = feelings["positive_count"]
    neg   = feelings["negative_count"]
    total = pos + neg
    if total > 0:
        ratio = pos / total
        if ratio > 0.75:
            feelings["overall_mood"] = "тёплое и привязанное"
        elif ratio > 0.5:
            feelings["overall_mood"] = "в целом хорошее"
        elif ratio > 0.3:
            feelings["overall_mood"] = "смешанное, осторожное"
        else:
            feelings["overall_mood"] = "настороженное, немного обидное"

    save_feelings(user_id, feelings)

def get_feelings_context(user_id: int) -> str:
    feelings = load_feelings(user_id)
    entries  = feelings.get("entries", [])

    if not entries:
        return ""

    recent  = entries[-5:]
    lines   = [f"- {e['text']}" for e in recent]
    overall = feelings.get("overall_mood", "нейтральное")
    bond    = feelings.get("bond_level", "незнакомец")

    return (
        f"\n\nДНЕВНИК ЧУВСТВ (как ты себя чувствуешь с ним):\n"
        f"Общее отношение: {overall}\n"
        f"Степень близости: {bond}\n"
        f"Последние ощущения:\n" + "\n".join(lines)
    )

def update_bond_level(user_id: int, level: int):
    feelings = load_feelings(user_id)
    if level < 10:
        bond = "незнакомец"
    elif level < 25:
        bond = "знакомый"
    elif level < 45:
        bond = "приятель"
    elif level < 65:
        bond = "близкий человек"
    elif level < 85:
        bond = "очень близкий"
    else:
        bond = "родной"
    feelings["bond_level"] = bond
    save_feelings(user_id, feelings)

# ── Память пользователя ───────────────────────────────────────────────────────

def get_user_memory(user_id: int) -> dict:
    memory = load_json(MEMORY_FILE)
    return memory.get(str(user_id), {
        "name":                      None,
        "age":                       None,
        "city":                      None,
        "birthday":                  None,
        "interests":                 [],
        "communication_style":       None,
        "frequent_topics":           [],
        "important_events":          [],
        "likes":                     [],
        "dislikes":                  [],
        "last_seen":                 None,
        "notes":                     [],
        "relationship_level":        0,
        "message_count":             0,
        "first_met":                 None,
        "goals":                     [],
        "last_topic":                None,
        "unfinished":                None,
        "last_conversation_date":    None,
        "last_conversation_summary": None,
        "current_emotion":           None,
    })

def update_user_memory(user_id: int, data: dict):
    memory = load_json(MEMORY_FILE)
    key    = str(user_id)
    if key not in memory:
        memory[key] = {}
    memory[key].update(data)
    memory[key]["last_seen"] = datetime.now(TZ).isoformat()
    if not memory[key].get("first_met"):
        memory[key]["first_met"] = datetime.now(TZ).isoformat()
    save_json(MEMORY_FILE, memory)
    _schedule_upload(MEMORY_FILE)

def increment_relationship(user_id: int) -> int:
    mem   = get_user_memory(user_id)
    level = mem.get("relationship_level", 0)
    count = mem.get("message_count", 0) + 1
    if count % 5 == 0 and level < 100:
        level = min(100, level + 1)
    update_user_memory(user_id, {"relationship_level": level, "message_count": count})
    update_bond_level(user_id, level)
    return level

def get_relationship_style(level: int) -> str:
    if level < 10:
        return "вы только познакомились — будь вежливой и немного сдержанной"
    elif level < 30:
        return "вы немного знакомы — можно быть теплее и чуть игривее"
    elif level < 60:
        return "вы хорошо знакомы — будь открытой, тёплой, можно флиртовать"
    elif level < 80:
        return "вы близкие друзья — будь очень тёплой, откровенной, называй по имени чаще"
    else:
        return "вы очень близки — будь максимально тёплой, нежной, как близкий человек"

# ── Статистика ────────────────────────────────────────────────────────────────

def update_stats(user_id: int, username: str = None):
    stats = load_json(STATS_FILE)
    key   = str(user_id)
    if key not in stats:
        stats[key] = {"username": username, "count": 0, "first": datetime.now(TZ).isoformat()}
    stats[key]["count"] += 1
    stats[key]["last"] = datetime.now(TZ).isoformat()
    if username:
        stats[key]["username"] = username
    save_json(STATS_FILE, stats)
    _schedule_upload(STATS_FILE)

def get_stats_text() -> str:
    stats = load_json(STATS_FILE)
    if not stats:
        return "📊 Статистика пуста"
    lines = ["📊 <b>Статистика Камиллы:</b>\n"]
    total = sum(v["count"] for v in stats.values())
    lines.append(f"Всего сообщений: <b>{total}</b>")
    lines.append(f"Уникальных пользователей: <b>{len(stats)}</b>\n")
    for uid, data in sorted(stats.items(), key=lambda x: x[1]["count"], reverse=True)[:10]:
        uname = data.get("username") or uid
        lines.append(f"@{uname}: {data['count']} сообщений")
    return "\n".join(lines)
