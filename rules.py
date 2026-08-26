# -*- coding: utf-8 -*-
"""Логика подбора комплекта лицензий и платформы по правилам офиса Марксистская.

Источник правил: файл «ПРАВИЛА-ОТГРУЗКИ.md» (раздел 7 — алгоритм подбора).
"""

import prices


def make_1c_licenses(need_rm):
    """Подбирает клиентские лицензии 1С ПОН на need_rm рабочих мест (минимальная стоимость)."""
    lic = sorted(prices.CLIENT_1C, key=lambda x: x["price"] / x["rm"])
    remaining = need_rm
    items = []
    for l in lic:
        if remaining <= 0:
            break
        n = remaining // l["rm"]
        if n:
            items.append({"name": l["name"], "qty": n, "unit": l["price"]})
            remaining -= n * l["rm"]
    if remaining > 0:
        one = next(l for l in prices.CLIENT_1C if l["rm"] == 1)
        items.append({"name": one["name"], "qty": remaining, "unit": one["price"]})
    return items


def make_bit_licenses(need_rm):
    """Лицензии для ТОР на need_rm рабочих мест (минимальная стоимость)."""
    order = sorted(prices.BIT_LIC, key=lambda x: x["price"] / x["rm"])
    remaining = need_rm
    items = []
    for l in order:
        if remaining <= 0:
            break
        n = remaining // l["rm"]
        if n:
            items.append({"name": f"БИТ.[ТОР]. Клиентская лицензия на {l['rm']} РМ. Эл.",
                          "qty": n, "unit": l["price"]})
            remaining -= n * l["rm"]
    if remaining > 0:
        one = next(l for l in prices.BIT_LIC if l["rm"] == 1)
        items.append({"name": f"БИТ.[ТОР]. Клиентская лицензия на 1 РМ. Эл.",
                      "qty": remaining, "unit": one["price"]})
    return items


def pick_bit_licenses(need_rm):
    return make_bit_licenses(need_rm)


def build_quote(tor_key=None, main_key=None, total_users=1, tor_users=None,
                client_server=False, has_platform=False, need_support_months=0):
    """Собирает комплект КП по правилам.

    Параметры:
      tor_key       — ключ из prices.TOR, если это ТОР
      main_key      — ключ основной поставки типового 1С (если не ТОР)
      total_users   — всего пользователей 1С
      tor_users     — сколько пользователей работают именно в ТОРе (только для ТОР, по умолч. = total_users)
      client_server — клиент-серверный режим (нужна лицензия на сервер)
      has_platform  — есть ли уже платформа/основная поставка у клиента
      support_months — срок сопровождения ТОР (6/12/18), 0 = не нужно

    Возвращает: (lines, total, warnings)
      lines  — список [наименование, кол-во, цена_ед, сумма]
      total  — итоговая сумма (int или None если есть «по запросу»)
      warnings — список примечаний
    """
    lines = []
    warnings = []

    # --- Основная поставка ---
    if tor_key is not None:
        t = prices.TOR[tor_key]
        lines.append([t["name"], 1, t["price"], t["price"]])
        included_bit = t["bit_rm"]
        included_1c = 0
    elif main_key is not None:
        m = prices.MAIN_1C_BUDGET.get(main_key) or prices.MAIN_1C_EDU.get(main_key) or prices.MAIN_1C.get(main_key)
        if not m:
            raise ValueError(f"Неизвестная основная поставка: {main_key}")
        lines.append([m["name"], 1, m["price"], m["price"]])
        included_1c = m.get("rm", 1)
        included_bit = 0
    else:
        raise ValueError("Не указан ни ТОР, ни основная поставка")

    # --- Платформа / технологическая поставка ---
    # Для ТОР самостоятельная конфигурация: нужна тех.поставка, если платформы нет
    if tor_key is not None and not has_platform:
        pt = prices.PLATFORM["tech"]
        lines.append([pt["name"], 1, pt["price"], pt["price"]])

    # --- Клиентские лицензии 1С ---
    need_1c = total_users - included_1c
    if need_1c > 0:
        for it in make_1c_licenses(need_1c):
            lines.append([it["name"], it["qty"], it["unit"], it["unit"] * it["qty"]])

    # --- БИТ-лицензии для ТОР ---
    if tor_key is not None:
        tor_need = tor_users if tor_users is not None else total_users
        need_bit = tor_need - included_bit
        if need_bit > 0:
            for it in pick_bit_licenses(need_bit):
                lines.append([it["name"], it["qty"], it["unit"], it["unit"] * it["qty"]])

    # --- Сервер ---
    if client_server:
        s = prices.SERVER["x86_64"]  # по умолч. x86-64
        lines.append([s["name"], 1, s["price"], s["price"]])
        if total_users <= 5:
            warnings.append("Для 5 и менее пользователей может подойти 1С:Сервер МИНИ (21 300 руб) — уточните.")

    # --- Сопровождение ТОР ---
    if need_support_months and need_support_months in prices.SUPPORT_TOR:
        sp = prices.SUPPORT_TOR[need_support_months]
        lines.append([sp["name"], 1, sp["price"], sp["price"]])

    # --- Итог ---
    total = None
    if all(isinstance(l[3], int) for l in lines):
        total = sum(l[3] for l in lines)
    return lines, total, warnings