"""
finance_parser.py — распознаёт финансовые команды из текста пользователя.
Примеры:
  "потратил 50000 на еду"        → расход 50000 "еда"
  "заработал 2 млн"              → доход 2000000
  "пришло 500к с проекта"        → доход 500000
  "отчёт за день"                → отчёт day
  "покажи расходы за неделю"     → отчёт week
  "баланс"                       → общий баланс
  "удали последнее"              → удалить последнюю запись
"""

import re

# ── Триггеры расхода ──────────────────────────────────────────────────────────

EXPENSE_TRIGGERS = [
    "потратил", "потратила", "купил", "купила", "заплатил", "заплатила",
    "расход", "трата", "ушло", "отдал", "отдала", "списал", "списала",
    "оплатил", "оплатила", "истратил", "истратила",
]

# ── Триггеры дохода ───────────────────────────────────────────────────────────

INCOME_TRIGGERS = [
    "заработал", "заработала", "получил", "получила", "пришло", "пришли",
    "доход", "выручка", "поступило", "выплатили", "перевели", "заработок",
    "продал", "продала", "прибыль", "заработок",
]

# ── Триггеры отчёта ───────────────────────────────────────────────────────────

REPORT_DAY_TRIGGERS   = ["за день", "за сегодня", "сегодня потратил", "сегодняшний"]
REPORT_WEEK_TRIGGERS  = ["за неделю", "за 7 дней", "недельный"]
REPORT_MONTH_TRIGGERS = ["за месяц", "за 30 дней", "месячный", "ежемесячный"]
BALANCE_TRIGGERS      = ["баланс", "общий баланс", "сколько денег", "сколько осталось", "итого"]
DELETE_TRIGGERS       = ["удали последнее", "отмени последнее", "удали запись", "убери последнее"]

# ── Парсинг суммы ─────────────────────────────────────────────────────────────

def parse_amount(text: str) -> float | None:
    """
    Извлекает сумму из текста.
    Поддерживает: 50000, 50к, 50К, 2 млн, 1.5млн, 500тыс
    """
    text = text.lower().replace(" ", "")

    # млн / миллион
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:млн|миллион)', text)
    if m:
        return float(m.group(1).replace(",", ".")) * 1_000_000

    # тыс / тысяч / к / k
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:тыс|тысяч|к|k)', text)
    if m:
        return float(m.group(1).replace(",", ".")) * 1_000

    # просто число
    m = re.search(r'(\d+(?:[.,]\d+)?)', text)
    if m:
        return float(m.group(1).replace(",", "."))

    return None


def parse_description(text: str, triggers: list) -> str:
    """Вырезает триггер и сумму, возвращает остаток как описание"""
    t = text.lower()
    for trigger in triggers:
        t = t.replace(trigger, "")

    # убираем суммы
    t = re.sub(r'\d+(?:[.,]\d+)?\s*(?:млн|миллион|тыс|тысяч|к|k)?', "", t)
    # убираем предлоги
    t = re.sub(r'\b(на|за|для|по|в|с|от|из|у)\b', "", t)
    # убираем лишние пробелы и знаки
    t = re.sub(r'[^а-яёa-z0-9\s]', "", t).strip()
    t = re.sub(r'\s+', " ", t).strip()

    return t if len(t) > 1 else ""


# ═══════════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ ФУНКЦИЯ РАСПОЗНАВАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

def detect_finance_command(text: str) -> dict | None:
    """
    Возвращает dict с командой или None если не финансовая команда.

    Форматы возврата:
      {"cmd": "expense", "amount": 50000, "description": "еда"}
      {"cmd": "income",  "amount": 500000, "description": "проект"}
      {"cmd": "report",  "period": "day" | "week" | "month"}
      {"cmd": "balance"}
      {"cmd": "delete_last"}
    """
    tl = text.lower()

    # ── Удалить последнее ──
    if any(t in tl for t in DELETE_TRIGGERS):
        return {"cmd": "delete_last"}

    # ── Баланс ──
    if any(t in tl for t in BALANCE_TRIGGERS):
        # не путаем с "баланс за день" → отчёт
        if not any(t in tl for t in ["за день", "за неделю", "за месяц"]):
            return {"cmd": "balance"}

    # ── Отчёты ──
    if any(t in tl for t in REPORT_DAY_TRIGGERS):
        return {"cmd": "report", "period": "day"}
    if any(t in tl for t in REPORT_WEEK_TRIGGERS):
        return {"cmd": "report", "period": "week"}
    if any(t in tl for t in REPORT_MONTH_TRIGGERS):
        return {"cmd": "report", "period": "month"}

    # ── Расход ──
    if any(t in tl for t in EXPENSE_TRIGGERS):
        amount = parse_amount(text)
        if amount:
            desc = parse_description(tl, EXPENSE_TRIGGERS)
            return {"cmd": "expense", "amount": amount, "description": desc}

    # ── Доход ──
    if any(t in tl for t in INCOME_TRIGGERS):
        amount = parse_amount(text)
        if amount:
            desc = parse_description(tl, INCOME_TRIGGERS)
            return {"cmd": "income", "amount": amount, "description": desc}

    return None
