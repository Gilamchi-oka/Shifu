"""
finance.py — учёт капитала: расходы, доходы, баланс, отчёты.
Хранение: JSON файл kamilla_finance.json
"""

import json, os
from datetime import datetime, timedelta
from config import TZ

FINANCE_FILE = "kamilla_finance.json"


# ═══════════════════════════════════════════════════════════════════════════════
# ЗАГРУЗКА / СОХРАНЕНИЕ
# ═══════════════════════════════════════════════════════════════════════════════

def _load() -> dict:
    if os.path.exists(FINANCE_FILE):
        with open(FINANCE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _save(data: dict):
    with open(FINANCE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _get_user(data: dict, user_id: int) -> dict:
    key = str(user_id)
    if key not in data:
        data[key] = {"transactions": []}
    return data[key]


# ═══════════════════════════════════════════════════════════════════════════════
# ДОБАВЛЕНИЕ ТРАНЗАКЦИЙ
# ═══════════════════════════════════════════════════════════════════════════════

def add_expense(user_id: int, amount: float, description: str = "") -> str:
    """Записать расход"""
    data = _load()
    user = _get_user(data, user_id)
    user["transactions"].append({
        "type":        "expense",
        "amount":      abs(amount),
        "description": description,
        "date":        datetime.now(TZ).strftime("%Y-%m-%d"),
        "time":        datetime.now(TZ).strftime("%H:%M"),
    })
    _save(data)
    return f"расход -{_fmt(amount)} | {description or '—'}"


def add_income(user_id: int, amount: float, description: str = "") -> str:
    """Записать доход"""
    data = _load()
    user = _get_user(data, user_id)
    user["transactions"].append({
        "type":        "income",
        "amount":      abs(amount),
        "description": description,
        "date":        datetime.now(TZ).strftime("%Y-%m-%d"),
        "time":        datetime.now(TZ).strftime("%H:%M"),
    })
    _save(data)
    return f"доход +{_fmt(amount)} | {description or '—'}"


# ═══════════════════════════════════════════════════════════════════════════════
# ОТЧЁТЫ
# ═══════════════════════════════════════════════════════════════════════════════

def get_report(user_id: int, period: str = "month") -> str:
    """
    period: 'day' | 'week' | 'month'
    Возвращает текстовый отчёт.
    """
    data = _load()
    user = _get_user(data, user_id)
    txs  = user.get("transactions", [])

    now   = datetime.now(TZ).date()
    if period == "day":
        since = now
        label = "сегодня"
    elif period == "week":
        since = now - timedelta(days=7)
        label = "за 7 дней"
    else:
        since = now - timedelta(days=30)
        label = "за 30 дней"

    filtered = [
        t for t in txs
        if datetime.strptime(t["date"], "%Y-%m-%d").date() >= since
    ]

    if not filtered:
        return f"данных {label} нет"

    income  = sum(t["amount"] for t in filtered if t["type"] == "income")
    expense = sum(t["amount"] for t in filtered if t["type"] == "expense")
    balance = income - expense

    sign   = "+" if balance >= 0 else "-"
    lines  = [
        f"отчёт {label}",
        f"доходы:  +{_fmt(income)}",
        f"расходы: -{_fmt(expense)}",
        f"баланс:  {sign}{_fmt(abs(balance))}",
    ]

    # последние 5 транзакций
    recent = filtered[-5:][::-1]
    if recent:
        lines.append("последние:")
        for t in recent:
            icon = "+" if t["type"] == "income" else "-"
            lines.append(f"  {icon}{_fmt(t['amount'])} {t['description'] or '—'} ({t['time']})")

    return "\n".join(lines)


def get_balance(user_id: int) -> str:
    """Текущий баланс за всё время"""
    data = _load()
    user = _get_user(data, user_id)
    txs  = user.get("transactions", [])

    if not txs:
        return "транзакций нет"

    income  = sum(t["amount"] for t in txs if t["type"] == "income")
    expense = sum(t["amount"] for t in txs if t["type"] == "expense")
    balance = income - expense
    sign    = "+" if balance >= 0 else "-"

    return (
        f"общий баланс: {sign}{_fmt(abs(balance))}\n"
        f"доходы: +{_fmt(income)}\n"
        f"расходы: -{_fmt(expense)}"
    )


def delete_last(user_id: int) -> str:
    """Удалить последнюю запись"""
    data = _load()
    user = _get_user(data, user_id)
    txs  = user.get("transactions", [])

    if not txs:
        return "нечего удалять"

    last = txs.pop()
    _save(data)
    icon = "+" if last["type"] == "income" else "-"
    return f"удалено: {icon}{_fmt(last['amount'])} {last['description'] or '—'}"


# ═══════════════════════════════════════════════════════════════════════════════
# ВСПОМОГАТЕЛЬНОЕ
# ═══════════════════════════════════════════════════════════════════════════════

def _fmt(amount: float) -> str:
    """Форматирует число: 1000000 → 1 000 000"""
    return f"{amount:,.0f}".replace(",", " ")
