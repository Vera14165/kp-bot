# -*- coding: utf-8 -*-
"""Логика подбора комплекта лицензий и платформы по правилам офиса Марксистская.

Источник правил: файл «ПРАВИЛА-ОТГРУЗКИ.md» (раздел 7 — алгоритм подбора).
"""

import prices


def _optimal_combo(need_rm, packs, make_name):
    """Находит самую дешёвую комбинацию пакетов лицензий, покрывающую need_rm рабочих мест.

    Перебирает все варианты (включая «взять пакет больше, чем нужно», если это дешевле)
    и возвращает список {"name", "qty", "unit"} с минимальной суммой.

    packs    — список {"rm": int, "price": int} доступных пакетов.
    make_name — функция: (rm, price) -> название позиции.
    """
    if need_rm <= 0:
        return []

    # Сортируем пакеты по размеру
    packs = sorted(packs, key=lambda x: x["rm"])
    max_rm = packs[-1]["rm"]
    limit = need_rm + max_rm  # больше набрать не имеет смысла

    INF = float("inf")
    # best[i] = минимальная стоимость, чтобы покрыть РОВНО i рабочих мест
    best = [INF] * (limit + 1)
    # choice[i] = (размер пакета, число пакетов) последнего шага
    choice = [None] * (limit + 1)
    best[0] = 0

    for i in range(limit + 1):
        if best[i] == INF:
            continue
        for p in packs:
            ni = i + p["rm"]
            if ni <= limit:
                cand = best[i] + p["price"]
                if cand < best[ni]:
                    best[ni] = cand
                    choice[ni] = p["rm"]

    # Выбираем покрытие с минимальной стоимостью (можно с запасом: от need_rm до limit)
    total_min = INF
    target = need_rm
    for i in range(need_rm, limit + 1):
        if best[i] < total_min:
            total_min = best[i]
            target = i

    # Восстанавливаем комбинацию
    counts = {}
    cur = target
    while cur > 0 and choice[cur] is not None:
        rm = choice[cur]
        counts[rm] = counts.get(rm, 0) + 1
        cur -= rm
    if cur != 0:  # крайний случай — страховка
        pass

    items = []
    for rm in sorted(counts):
        price = next(p["price"] for p in packs if p["rm"] == rm)
        items.append({"name": make_name(rm, price), "qty": counts[rm], "unit": price})
    return items


def make_1c_licenses(need_rm):
    """Клиентские лицензии 1С ПРОФ на need_rm рабочих мест — самая выгодная комбинация."""
    packs = [{"rm": l["rm"], "price": l["price"]} for l in prices.CLIENT_1C]
    return _optimal_combo(need_rm, packs, lambda rm, price: next(
        l["name"] for l in prices.CLIENT_1C if l["rm"] == rm))


def make_bit_licenses(need_rm):
    """БИТ-лицензии для ТОР на need_rm рабочих мест — самая выгодная комбинация."""
    packs = [{"rm": l["rm"], "price": l["price"]} for l in prices.BIT_LIC]
    return _optimal_combo(
        need_rm, packs,
        lambda rm, price: f"БИТ.[ТОР]. Клиентская лицензия на {rm} РМ. Эл.")


def pick_bit_licenses(need_rm):
    return make_bit_licenses(need_rm)


def build_quote(tor_key=None, main_key=None, total_users=1, tor_users=None,
                client_server=False, has_platform=False, need_support_months=0,
                has_server=False):
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
        warnings.append(
            "* Технологическая поставка нужна, если система будет развёрнута ОТДЕЛЬНО от других "
            "систем на платформе 1С (для ТОРов). Если ТОР размещается в одной локальной сети с "
            "уже купленной платформой 1С — тех.поставка не требуется."
        )

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
    # Если клиент-сервер и у клиента НЕТ своей лицензии на сервер — добавляем
    if client_server and not has_server:
        s = prices.SERVER["x86_64"]  # по умолч. x86-64
        lines.append([s["name"], 1, s["price"], s["price"]])
        if total_users <= 15:
            warnings.append("Для небольших сетей может подойти 1С:Сервер МИНИ на 5 подключений (21 300 руб) — уточните.")

    # --- Сопровождение ТОР ---
    if need_support_months and need_support_months in prices.SUPPORT_TOR:
        sp = prices.SUPPORT_TOR[need_support_months]
        lines.append([sp["name"], 1, sp["price"], sp["price"]])

    # --- Итог ---
    total = None
    if all(isinstance(l[3], int) for l in lines):
        total = sum(l[3] for l in lines)
    return lines, total, warnings
