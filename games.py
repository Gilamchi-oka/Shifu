"""
games.py — мини-игры: города, угадай число, виселица, матем. спринт, крестики-нолики
Подключается в main.py
"""

import json, os, random, re, time
from datetime import datetime

GAMES_FILE = "kamilla_games.json"

# ═══════════════════════════════════════════════════════════════════════════════
# ХРАНИЛИЩЕ
# ═══════════════════════════════════════════════════════════════════════════════

def _load() -> dict:
    if os.path.exists(GAMES_FILE):
        with open(GAMES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save(data: dict):
    with open(GAMES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_game(user_id: int) -> dict | None:
    return _load().get(str(user_id))

def set_game(user_id: int, game: dict | None):
    data = _load()
    if game is None:
        data.pop(str(user_id), None)
    else:
        data[str(user_id)] = game
    _save(data)

def is_game_active(user_id: int) -> bool:
    return get_game(user_id) is not None

# ═══════════════════════════════════════════════════════════════════════════════
# ОПРЕДЕЛЕНИЕ ТРИГГЕРОВ
# ═══════════════════════════════════════════════════════════════════════════════

GAME_TRIGGERS = {
    "cities": [
        "сыграем в города", "давай в города", "игра в города",
        "играем в города", "поиграем в города", "city game",
    ],
    "number": [
        "загадай число", "угадай число", "игра в число",
        "сыграем в число", "поиграем угадай число", "угадывай число",
    ],
    "hangman": [
        "сыграем в виселицу", "давай в виселицу", "виселица",
        "игра в виселицу", "поиграем в виселицу", "hangman",
    ],
    "mathsprint": [
        "математический спринт", "матем спринт", "math sprint",
        "сыграем в математику", "давай в математику", "считаем на скорость",
        "игра в математику", "матспринт", "поиграем в математику",
    ],
    "tictactoe": [
        "крестики нолики", "крестики-нолики", "tic tac toe", "tictactoe",
        "сыграем в крестики", "давай в крестики", "игра в крестики",
        "поиграем в крестики", "сыграем в нолики",
    ],
}

STOP_TRIGGERS = ["стоп игра", "хватит играть", "заканчиваем игру", "выход из игры", "stop game"]

def detect_game_start(text: str) -> str | None:
    """Возвращает тип игры или None"""
    t = text.lower()
    for game_type, triggers in GAME_TRIGGERS.items():
        if any(tr in t for tr in triggers):
            return game_type
    return None

def detect_game_stop(text: str) -> bool:
    t = text.lower()
    return any(tr in t for tr in STOP_TRIGGERS)

# ═══════════════════════════════════════════════════════════════════════════════
# ИГРА: ГОРОДА
# ═══════════════════════════════════════════════════════════════════════════════

CITIES = [
    "москва", "санкт-петербург", "новосибирск", "екатеринбург", "казань",
    "нижний новгород", "челябинск", "самара", "омск", "ростов-на-дону",
    "уфа", "красноярск", "пермь", "воронеж", "волгоград",
    "ташкент", "самарканд", "бухара", "наманган", "андижан",
    "алматы", "астана", "шымкент", "актобе", "тараз",
    "минск", "гомель", "витебск", "могилёв", "брест",
    "киев", "харьков", "одесса", "днепр", "запорожье",
    "лондон", "париж", "берлин", "рим", "мадрид",
    "барселона", "амстердам", "вена", "прага", "варшава",
    "стамбул", "анкара", "дубай", "токио", "пекин",
    "шанхай", "сеул", "бангкок", "сингапур", "джакарта",
    "дели", "мумбаи", "карачи", "лахор", "исламабад",
    "каир", "лагос", "найроби", "йоханнесбург", "касабланка",
    "нью-йорк", "лос-анджелес", "чикаго", "хьюстон", "феникс",
    "торонто", "монреаль", "ванкувер", "мехико", "сан-паулу",
    "рио-де-жанейро", "буэнос-айрес", "богота", "лима", "сантьяго",
    "sydney", "melbourne", "brisbane",
    "нурсултан", "бишкек", "душанбе", "ашхабад", "баку",
    "тбилиси", "ереван", "кишинёв", "рига", "таллин", "вильнюс",
]

def _get_last_letter(city: str) -> str:
    """Возвращает последнюю значимую букву города (не ь, ъ, й)"""
    skip = set("ьъй")
    for ch in reversed(city.replace("-", "").replace(" ", "")):
        if ch not in skip:
            return ch
    return city[-1]

def cities_start(user_id: int) -> str:
    first = random.choice(["Москва", "Ташкент", "Алматы", "Берлин", "Токио"])
    game = {
        "type":      "cities",
        "used":      [first.lower()],
        "last_city": first.lower(),
        "score":     0,
        "started":   datetime.now().isoformat(),
    }
    set_game(user_id, game)
    last_letter = _get_last_letter(first.lower()).upper()
    return (
        f"🏙 играем в города! я начну\n"
        f"моё: **{first}**\n"
        f"твой ход — на букву **{last_letter}**\n"
        f"(«стоп игра» чтобы закончить)"
    )

def cities_move(user_id: int, text: str) -> str:
    game = get_game(user_id)
    if not game or game["type"] != "cities":
        return ""

    city = text.strip().lower()
    city = re.sub(r'[^\w\s-]', '', city).strip()

    if len(city) < 2 or len(city) > 30:
        return ""

    last = game["last_city"]
    needed_letter = _get_last_letter(last)

    if city[0] != needed_letter:
        return f"город должен начинаться на **{needed_letter.upper()}** 😏 попробуй ещё"

    if city not in CITIES:
        if re.search(r'\d', city) or len(city.split()) > 3:
            return f"хм, не знаю такого города 🤔"

    if city in game["used"]:
        return f"**{city.capitalize()}** уже называли! другой город на **{needed_letter.upper()}**"

    game["used"].append(city)
    game["score"] += 1

    bot_letter = _get_last_letter(city)
    bot_options = [c for c in CITIES if c[0] == bot_letter and c not in game["used"]]

    if not bot_options:
        set_game(user_id, None)
        return (
            f"✅ **{city.capitalize()}** — принято!\n"
            f"не могу придумать город на **{bot_letter.upper()}**... ты выиграл 🎉\n"
            f"счёт: {game['score']} городов"
        )

    bot_city = random.choice(bot_options)
    game["used"].append(bot_city)
    game["last_city"] = bot_city
    next_letter = _get_last_letter(bot_city).upper()
    set_game(user_id, game)

    return (
        f"✅ **{city.capitalize()}** — окей!\n"
        f"моё: **{bot_city.capitalize()}**\n"
        f"твой ход — на **{next_letter}**"
    )

# ═══════════════════════════════════════════════════════════════════════════════
# ИГРА: УГАДАЙ ЧИСЛО
# ═══════════════════════════════════════════════════════════════════════════════

def number_start(user_id: int) -> str:
    modes = [
        (1, 50,  "от 1 до 50"),
        (1, 100, "от 1 до 100"),
        (1, 20,  "от 1 до 20 — лёгкий режим 😏"),
    ]
    lo, hi, label = random.choice(modes)
    number = random.randint(lo, hi)
    game = {
        "type":     "number",
        "number":   number,
        "lo":       lo,
        "hi":       hi,
        "attempts": 0,
        "max_attempts": 7,
    }
    set_game(user_id, game)
    return (
        f"🎲 загадала число {label}\n"
        f"у тебя 7 попыток. называй!"
    )

def number_guess(user_id: int, text: str) -> str:
    game = get_game(user_id)
    if not game or game["type"] != "number":
        return ""

    m = re.search(r'\d+', text)
    if not m:
        return ""

    guess = int(m.group())
    secret = game["number"]
    game["attempts"] += 1
    attempts = game["attempts"]
    max_att  = game["max_attempts"]
    left     = max_att - attempts

    if guess == secret:
        set_game(user_id, None)
        if attempts == 1:
            return f"😱 с первой попытки?! угадал! число было **{secret}**"
        elif attempts <= 3:
            return f"🔥 угадал за {attempts} попытки! число **{secret}**. быстро!"
        else:
            return f"✅ угадал за {attempts} попыток! число было **{secret}**"

    if attempts >= max_att:
        set_game(user_id, None)
        return f"😄 попытки кончились! загадала **{secret}**. в другой раз повезёт"

    if guess < secret:
        hints = ["больше", "выше", "маловато", "побольше 👆"]
    else:
        hints = ["меньше", "ниже", "многовато", "поменьше 👇"]

    hint = random.choice(hints)

    extra = ""
    if left <= 2:
        if guess < secret:
            extra = f" (диапазон {guess+1}–{game['hi']})"
        else:
            extra = f" (диапазон {game['lo']}–{guess-1})"

    set_game(user_id, game)
    return f"{hint}{extra} — осталось попыток: {left}"

# ═══════════════════════════════════════════════════════════════════════════════
# ИГРА: ВИСЕЛИЦА
# ═══════════════════════════════════════════════════════════════════════════════

HANGMAN_WORDS = [
    ("аниме", "жанр японской анимации"),
    ("дракон", "мифическое существо с крыльями"),
    ("космос", "бесконечное пространство"),
    ("мечта", "то к чему стремишься"),
    ("загадка", "вопрос требующий разгадки"),
    ("приключение", "захватывающее путешествие"),
    ("характер", "совокупность черт личности"),
    ("интуиция", "чувство без объяснений"),
    ("вдохновение", "творческий порыв"),
    ("гармония", "согласие и равновесие"),
    ("таинство", "скрытая тайна"),
    ("вселенная", "всё что существует"),
    ("бесконечность", "то что не имеет конца"),
    ("волшебство", "чудесное явление"),
    ("путешествие", "поездка в далёкие края"),
    ("одиночество", "состояние без компании"),
    ("воображение", "способность представлять"),
    ("настроение", "эмоциональное состояние"),
    ("сюрприз", "неожиданный подарок"),
    ("секрет", "то что скрывают"),
    ("победа", "успешный результат борьбы"),
    ("свобода", "отсутствие ограничений"),
    ("загадочный", "непонятный и таинственный"),
    ("звезда", "светящееся тело в космосе"),
    ("музыка", "искусство звуков"),
]

HANGMAN_STAGES = [
    "⬜⬜⬜\n⬜😵⬜  конец!\n⬜⬜⬜",
    "⬜|⬜\n⬜😰⬜\n⬜/\\⬜",
    "⬜|⬜\n⬜😰⬜\n⬜/⬜⬜",
    "⬜|⬜\n/😰⬜\n⬜⬜⬜",
    "⬜|⬜\n/😨\\\n⬜⬜⬜",
    "⬜|⬜\n⬜😅\\\n⬜⬜⬜",
    "⬜|⬜\n⬜🙂⬜\n⬜⬜⬜",
    "⬜|⬜\n⬜😊⬜\n⬜⬜⬜",
]

def hangman_start(user_id: int) -> str:
    word, hint = random.choice(HANGMAN_WORDS)
    game = {
        "type":    "hangman",
        "word":    word,
        "hint":    hint,
        "guessed": [],
        "wrong":   [],
        "max_wrong": 6,
    }
    set_game(user_id, game)
    display = " ".join("_" * len(word))
    return (
        f"🎭 виселица!\n"
        f"слово: **{display}** ({len(word)} букв)\n"
        f"подсказка: _{hint}_\n"
        f"называй буквы по одной"
    )

def _hangman_display(game: dict) -> str:
    word    = game["word"]
    guessed = set(game["guessed"])
    wrong   = game["wrong"]
    wrong_count = len(wrong)
    stage_idx   = max(0, len(HANGMAN_STAGES) - 1 - wrong_count)
    stage       = HANGMAN_STAGES[stage_idx]

    display = " ".join(ch if ch in guessed else "_" for ch in word)
    wrong_str = " ".join(wrong) if wrong else "—"

    return f"{stage}\n\n**{display}**\nневерные: {wrong_str}"

def hangman_guess(user_id: int, text: str) -> str:
    game = get_game(user_id)
    if not game or game["type"] != "hangman":
        return ""

    text = text.strip().lower()

    if len(text) != 1 or not text.isalpha():
        return ""

    letter  = text
    word    = game["word"]
    guessed = game["guessed"]
    wrong   = game["wrong"]

    if letter in guessed or letter in wrong:
        return f"букву **{letter}** уже называли, другую"

    if letter in word:
        guessed.append(letter)
        game["guessed"] = guessed

        if all(ch in guessed for ch in word):
            set_game(user_id, None)
            return f"🎉 угадал! слово было **{word}**\n_{game['hint']}_"

        display = _hangman_display(game)
        set_game(user_id, game)
        return f"✅ есть буква **{letter}**!\n\n{display}"
    else:
        wrong.append(letter)
        game["wrong"] = wrong
        wrong_count   = len(wrong)
        max_wrong     = game["max_wrong"]

        if wrong_count >= max_wrong:
            set_game(user_id, None)
            return f"😵 виселица! слово было **{word}**\n_{game['hint']}_"

        display = _hangman_display(game)
        left    = max_wrong - wrong_count
        set_game(user_id, game)
        return f"❌ нет буквы **{letter}** (осталось {left} ошибок)\n\n{display}"

# ═══════════════════════════════════════════════════════════════════════════════
# ИГРА: МАТЕМАТИЧЕСКИЙ СПРИНТ
# ═══════════════════════════════════════════════════════════════════════════════
#
# Режимы сложности:
#   easy   — сложение/вычитание, числа 1–20, 10 примеров, 90 сек
#   normal — +/−/×, числа 1–20, 10 примеров, 60 сек
#   hard   — +/−/×/÷, числа 1–30, 15 примеров, 60 сек
#
# Бот присылает пример, игрок отвечает числом.
# Считается кол-во правильных ответов + затраченное время.
# При истечении времени — автофиниш.

MATH_MODES = {
    "easy":   {"ops": ["+", "-"],          "lo": 1,  "hi": 20, "total": 10, "time": 90},
    "normal": {"ops": ["+", "-", "×"],     "lo": 1,  "hi": 20, "total": 10, "time": 60},
    "hard":   {"ops": ["+", "-", "×", "÷"],"lo": 1,  "hi": 30, "total": 15, "time": 60},
}

MATH_TRIGGERS_EASY   = ["лёгкий", "легкий", "easy",   "просто"]
MATH_TRIGGERS_HARD   = ["сложный", "сложно", "hard",  "хардкор"]
# всё остальное → normal

def _make_example(mode_cfg: dict) -> tuple[str, int]:
    """Генерирует пример и правильный ответ."""
    lo, hi = mode_cfg["lo"], mode_cfg["hi"]
    op = random.choice(mode_cfg["ops"])

    if op == "+":
        a, b = random.randint(lo, hi), random.randint(lo, hi)
        return f"{a} + {b}", a + b

    elif op == "-":
        a, b = random.randint(lo, hi), random.randint(lo, hi)
        if a < b:
            a, b = b, a          # избегаем отрицательных
        return f"{a} - {b}", a - b

    elif op == "×":
        a = random.randint(2, min(hi, 12))
        b = random.randint(2, min(hi, 12))
        return f"{a} × {b}", a * b

    else:  # ÷
        b = random.randint(2, 10)
        answer = random.randint(2, 12)
        a = b * answer           # делимое всегда делится без остатка
        return f"{a} ÷ {b}", answer


def mathsprint_start(user_id: int, text: str = "") -> str:
    t = text.lower()
    if any(tr in t for tr in MATH_TRIGGERS_EASY):
        mode = "easy"
    elif any(tr in t for tr in MATH_TRIGGERS_HARD):
        mode = "hard"
    else:
        mode = "normal"

    cfg = MATH_MODES[mode]
    expr, answer = _make_example(cfg)

    game = {
        "type":      "mathsprint",
        "mode":      mode,
        "cfg":       cfg,
        "expr":      expr,
        "answer":    answer,
        "current":   1,           # номер текущего примера
        "correct":   0,
        "wrong":     0,
        "started_at": time.time(),
    }
    set_game(user_id, game)

    mode_labels = {"easy": "лёгкий 😊", "normal": "нормальный 🧠", "hard": "хардкор 🔥"}
    return (
        f"⚡ математический спринт! режим: {mode_labels[mode]}\n"
        f"{cfg['total']} примеров · {cfg['time']} сек\n\n"
        f"**{game['current']}/{cfg['total']}** → {expr} = ?"
    )


def _mathsprint_finish(game: dict) -> str:
    elapsed = time.time() - game["started_at"]
    correct = game["correct"]
    total   = game["cfg"]["total"]
    mins    = int(elapsed) // 60
    secs    = int(elapsed) % 60
    time_str = f"{mins}:{secs:02d}" if mins else f"{secs} сек"

    if correct == total:
        verdict = "🏆 идеально! все верно!"
    elif correct >= total * 0.8:
        verdict = "🔥 отлично!"
    elif correct >= total * 0.5:
        verdict = "👍 неплохо"
    else:
        verdict = "😅 тяжеловато"

    return (
        f"{verdict}\n"
        f"✅ правильно: {correct}/{total}\n"
        f"⏱ время: {time_str}"
    )


def mathsprint_answer(user_id: int, text: str) -> str:
    game = get_game(user_id)
    if not game or game["type"] != "mathsprint":
        return ""

    # Проверяем таймаут
    elapsed = time.time() - game["started_at"]
    if elapsed > game["cfg"]["time"]:
        result = _mathsprint_finish(game)
        set_game(user_id, None)
        return f"⏰ время вышло!\n{result}"

    # Извлекаем число из ответа
    m = re.search(r'-?\d+', text)
    if not m:
        return ""

    user_answer = int(m.group())
    correct_answer = game["answer"]
    current = game["current"]
    total   = game["cfg"]["total"]

    if user_answer == correct_answer:
        game["correct"] += 1
        reaction = random.choice(["✅", "✅ верно!", "🔥", "✅ так держать!"])
    else:
        game["wrong"] += 1
        reaction = f"❌ нет, было **{correct_answer}**"

    # Последний пример?
    if current >= total:
        game["correct"] = game["correct"]  # уже обновили выше
        result = _mathsprint_finish(game)
        set_game(user_id, None)
        return f"{reaction}\n\n{result}"

    # Следующий пример
    game["current"] += 1
    expr, answer = _make_example(game["cfg"])
    game["expr"]   = expr
    game["answer"] = answer

    time_left = int(game["cfg"]["time"] - elapsed)
    set_game(user_id, game)

    return f"{reaction}\n**{game['current']}/{total}** → {expr} = ?  _(осталось {time_left} сек)_"


# ═══════════════════════════════════════════════════════════════════════════════
# ИГРА: КРЕСТИКИ-НОЛИКИ
# ═══════════════════════════════════════════════════════════════════════════════
#
# Поле 3×3, пронумеровано:
#   1 | 2 | 3
#   4 | 5 | 6
#   7 | 8 | 9
#
# Игрок — ❌, бот — ⭕
# Бот играет по алгоритму: сначала побеждает, потом блокирует,
# потом ходит по стратегии (центр → углы → середины сторон).

_WIN_LINES = [
    (0,1,2),(3,4,5),(6,7,8),   # строки
    (0,3,6),(1,4,7),(2,5,8),   # столбцы
    (0,4,8),(2,4,6),           # диагонали
]

def _board_str(board: list[str]) -> str:
    """Рендерит доску в текст."""
    icons = {
        "X": "❌", "O": "⭕",
        "1":"1️⃣","2":"2️⃣","3":"3️⃣",
        "4":"4️⃣","5":"5️⃣","6":"6️⃣",
        "7":"7️⃣","8":"8️⃣","9":"9️⃣",
    }
    cells = [icons.get(c, c) for c in board]
    return (
        f"{cells[0]}{cells[1]}{cells[2]}\n"
        f"{cells[3]}{cells[4]}{cells[5]}\n"
        f"{cells[6]}{cells[7]}{cells[8]}"
    )

def _check_winner(board: list[str]) -> str | None:
    """Возвращает 'X', 'O' или None."""
    for a, b, c in _WIN_LINES:
        if board[a] == board[b] == board[c] and board[a] in ("X", "O"):
            return board[a]
    return None

def _is_draw(board: list[str]) -> bool:
    return all(c in ("X", "O") for c in board)

def _bot_move(board: list[str]) -> int:
    """Возвращает индекс (0-8) хода бота."""
    free = [i for i, c in enumerate(board) if c not in ("X", "O")]

    # 1. Выигрываем
    for i in free:
        board[i] = "O"
        if _check_winner(board) == "O":
            board[i] = str(i+1)
            return i
        board[i] = str(i+1)

    # 2. Блокируем игрока
    for i in free:
        board[i] = "X"
        if _check_winner(board) == "X":
            board[i] = str(i+1)
            return i
        board[i] = str(i+1)

    # 3. Стратегия: центр → углы → стороны
    preferred = [4, 0, 2, 6, 8, 1, 3, 5, 7]
    for i in preferred:
        if i in free:
            return i

    return free[0]


def tictactoe_start(user_id: int) -> str:
    board = [str(i+1) for i in range(9)]   # ["1","2",...,"9"]
    game = {
        "type":  "tictactoe",
        "board": board,
        "moves": 0,
    }
    set_game(user_id, game)
    return (
        f"♟ крестики-нолики!\n"
        f"ты — ❌, я — ⭕\n"
        f"называй цифру клетки (1–9)\n\n"
        f"{_board_str(board)}"
    )


def tictactoe_move(user_id: int, text: str) -> str:
    game = get_game(user_id)
    if not game or game["type"] != "tictactoe":
        return ""

    # Ищем цифру 1-9
    m = re.search(r'[1-9]', text)
    if not m:
        return ""

    idx = int(m.group()) - 1
    board = game["board"]

    # Клетка занята?
    if board[idx] in ("X", "O"):
        return f"клетка {idx+1} занята, выбери другую"

    # Ход игрока
    board[idx] = "X"
    game["moves"] += 1

    winner = _check_winner(board)
    if winner == "X":
        set_game(user_id, None)
        return f"🎉 ты выиграл!\n\n{_board_str(board)}"

    if _is_draw(board):
        set_game(user_id, None)
        return f"🤝 ничья!\n\n{_board_str(board)}"

    # Ход бота
    bot_idx = _bot_move(board)
    board[bot_idx] = "O"

    winner = _check_winner(board)
    if winner == "O":
        set_game(user_id, None)
        return f"😏 я выиграла!\n\n{_board_str(board)}"

    if _is_draw(board):
        set_game(user_id, None)
        return f"🤝 ничья!\n\n{_board_str(board)}"

    game["board"] = board
    set_game(user_id, game)

    return f"{_board_str(board)}\n\nтвой ход (1–9)"


# ═══════════════════════════════════════════════════════════════════════════════
# ЕДИНАЯ ТОЧКА ВХОДА
# ═══════════════════════════════════════════════════════════════════════════════

def handle_game_input(user_id: int, text: str) -> str | None:
    """
    Обрабатывает ввод пользователя если идёт игра.
    Возвращает ответ или None если игра не обработала сообщение.
    """
    game = get_game(user_id)
    if not game:
        return None

    game_type = game["type"]

    if game_type == "cities":
        result = cities_move(user_id, text)
        return result if result else None

    elif game_type == "number":
        result = number_guess(user_id, text)
        return result if result else None

    elif game_type == "hangman":
        result = hangman_guess(user_id, text)
        return result if result else None

    elif game_type == "mathsprint":
        result = mathsprint_answer(user_id, text)
        return result if result else None

    elif game_type == "tictactoe":
        result = tictactoe_move(user_id, text)
        return result if result else None

    return None


def start_game(user_id: int, game_type: str, text: str = "") -> str:
    """Запускает игру по типу"""
    if is_game_active(user_id):
        set_game(user_id, None)

    if game_type == "cities":
        return cities_start(user_id)
    elif game_type == "number":
        return number_start(user_id)
    elif game_type == "hangman":
        return hangman_start(user_id)
    elif game_type == "mathsprint":
        return mathsprint_start(user_id, text)
    elif game_type == "tictactoe":
        return tictactoe_start(user_id)
    return "не знаю такую игру"


def stop_game(user_id: int) -> str:
    game = get_game(user_id)
    if not game:
        return "игры нет"
    names = {
        "cities":     "города",
        "number":     "угадай число",
        "hangman":    "виселица",
        "mathsprint": "математический спринт",
        "tictactoe":  "крестики-нолики",
    }
    name = names.get(game["type"], "игра")
    set_game(user_id, None)
    return f"игра «{name}» остановлена"