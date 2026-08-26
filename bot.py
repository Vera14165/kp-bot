# -*- coding: utf-8 -*-
"""Telegram-бот расчёта КП (офис Марксистская).
Запуск: python bot.py
Для прода на хостинге: RUN_MODE=web WEBHOOK_URL=https://... PORT=8080 python bot.py
"""
import os
import logging

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

import prices
import rules

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("kpbot")

# Загрузка переменных из файла .env (если он есть рядом)
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
RUN_MODE = os.getenv("RUN_MODE", "poll")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", "8080"))
ALLOWED = {int(x) for x in os.getenv("ALLOWED_IDS", "").split(",") if x.strip()}

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ------- Список продуктов -------
TOR_KEYS = {
    "БИТ.Наука": "наука",
    "БИТ.Финансы ГУ": "финансы_гу",
    "БИТ.ВУЗ. Приемная комиссия": "вуз_приемная",
    "БИТ.ВУЗ. Учебная часть": "вуз_учебная",
    "БИТ.ВУЗ. Расписание": "вуз_расписание",
    "БИТ.Общежитие": "общежитие",
    "БИТ.Расчеты со студентами": "расчеты_со_студентами",
    "БИТ.УМЦ ПРОФ (5 РМ)": "умц_проф_5",
    "БИТ.УМЦ КОРП (5 РМ)": "умц_корп_5",
    "БИТ.Стоматология (3 РМ)": "стоматология_3",
}
MAIN_KEYS = {
    "Бухгалтерия 8 ПРОФ": "бухгалтерия_проф",
    "Бухгалтерия 8 КОРП": "бухгалтерия_корп",
    "Бухгалтерия 8 Комплект 5": "бухгалтерия_комп5",
    "ЗУП 8": "зуп",
    "ЗУП 8 КОРП": "зуп_корп",
    "Управление торговлей": "ут",
    "Документооборот 8 ПРОФ": "документооборот",
    "БГУ (бюджет)": "бгу",
    "ЗКГУ (бюджет)": "зкгу",
    "УНФ 8 ПРОФ": "унф",
    "УНФ 8 на 5": "унф_5",
}

# ------- Состояния -------
class KPD(StatesGroup):
    product_choice = State()
    total_users = State()
    tor_users = State()
    platform = State()
    server = State()
    support = State()

# ------- Вспомогательные -------
def fmt(n):
    return f"{n:,}".replace(",", " ") if n is not None else "по запросу"

def parse_int(s):
    try:
        return int(s.strip().replace(" ", ""))
    except Exception:
        return None

def kb_products():
    rows = [[KeyboardButton(text=t)] for t in list(TOR_KEYS) + list(MAIN_KEYS)]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def kb_yes_no():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton("Да"), KeyboardButton("Нет")]], resize_keyboard=True
    )

def kb_server():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton("Файловый"), KeyboardButton("Клиент-сервер")]],
        resize_keyboard=True,
    )

def kb_support():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton("Не нужно")],
            [KeyboardButton("6 мес."), KeyboardButton("12 мес."), KeyboardButton("18 мес.")],
        ],
        resize_keyboard=True,
    )

# ------- Хендлеры -------
@dp.message(CommandStart())
async def start(m: Message, state: FSMContext):
    if ALLOWED and m.from_user.id not in ALLOWED:
        await m.answer("Доступ запрещён. Обратитесь к администратору.")
        return
    await state.set_state(KPD.product_choice)
    await m.answer(
        "Привет! Я помогу собрать КП по 1С/БИТ.\n\nВыберите продукт:",
        reply_markup=kb_products(),
    )

@dp.message(KPD.product_choice)
async def on_product(m: Message, state: FSMContext):
    t = m.text.strip()
    if t in TOR_KEYS:
        await state.update_data(kind="tor", product=TOR_KEYS[t])
    elif t in MAIN_KEYS:
        await state.update_data(kind="main", product=MAIN_KEYS[t])
    else:
        await m.answer("Выберите продукт из кнопок.")
        return
    await state.set_state(KPD.total_users)
    await m.answer("Сколько всего пользователей 1С?", reply_markup=ReplyKeyboardRemove())


@dp.message(KPD.total_users)
async def on_users(m: Message, state: FSMContext):
    n = parse_int(m.text)
    if n is None or n < 1:
        await m.answer("Введите число (например: 8).")
        return
    await state.update_data(total_users=n)
    d = await state.get_data()
    if d.get("kind") == "tor":
        await state.set_state(KPD.tor_users)
        await m.answer(f"Сколько пользователей работают именно в ТОРе? (если все — отправьте {n})")
    else:
        await state.set_state(KPD.platform)
        await m.answer("Платформа 1С уже есть?", reply_markup=kb_yes_no())


@dp.message(KPD.tor_users)
async def on_tor_users(m: Message, state: FSMContext):
    n = parse_int(m.text)
    if n is None or n < 1:
        await m.answer("Введите число.")
        return
    await state.update_data(tor_users=n)
    await state.set_state(KPD.platform)
    await m.answer("Платформа 1С уже есть?", reply_markup=kb_yes_no())


@dp.message(KPD.platform)
async def on_platform(m: Message, state: FSMContext):
    t = m.text.strip().lower()
    if t not in ("да", "нет"):
        await m.answer("Ответьте «Да» или «Нет».")
        return
    await state.update_data(has_platform=(t == "да"))
    await state.set_state(KPD.server)
    await m.answer("Режим работы?", reply_markup=kb_server())


@dp.message(KPD.server)
async def on_server(m: Message, state: FSMContext):
    t = m.text.strip().lower()
    if t not in ("файловый", "клиент-сервер"):
        await m.answer("Выберите режим из кнопок.")
        return
    await state.update_data(client_server=(t == "клиент-сервер"))
    d = await state.get_data()
    if d.get("kind") == "tor":
        await state.set_state(KPD.support)
        await m.answer("Нужно сопровождение ТОР (ПТС)?", reply_markup=kb_support())
    else:
        await calc_and_send(m, state)


@dp.message(KPD.support)
async def on_support(m: Message, state: FSMContext):
    months = {"не нужно": 0, "6 мес.": 6, "12 мес.": 12, "18 мес.": 18}
    t = m.text.strip().lower()
    if t not in months:
        await m.answer("Выберите из кнопок.")
        return
    await state.update_data(support_months=months[t])
    await calc_and_send(m, state)


async def calc_and_send(m: Message, state: FSMContext):
    d = await state.get_data()
    try:
        kw = {
            "total_users": d.get("total_users", 1),
            "client_server": d.get("client_server", False),
            "has_platform": d.get("has_platform", False),
        }
        if d.get("kind") == "tor":
            kw["tor_key"] = d["product"]
            kw["tor_users"] = d.get("tor_users", kw["total_users"])
            kw["need_support_months"] = d.get("support_months", 0)
        else:
            kw["main_key"] = d["product"]

        lines, total_sum, warns = rules.build_quote(**kw)
    except Exception as e:
        log.exception("Calc error")
        await m.answer("Ошибка расчёта. Попробуйте /start.")
        await state.clear()
        return

    out = ["<b>Расчёт КП</b>\n"]
    for i, (name, qty, unit, s) in enumerate(lines, 1):
        out.append(f"{i}. {name}\n      ×{qty} | {fmt(unit)} руб | <b>{fmt(s)} руб</b>")
    if total_sum is not None:
        out.append(f"\n<b>ИТОГО: {fmt(total_sum)} руб</b>")
    else:
        out.append("\n<b>ИТОГО: часть цен «по запросу»</b>")
    for w in warns:
        out.append(f"\n⚠ {w}")
    out.append("\n📌 Позиции 1С — по разрешению в 1С; ТОР — через Внутренний заказ в К7.")

    await m.answer("\n".join(out), parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await state.clear()


# ------- Запуск -------
async def main():
    if RUN_MODE == "web":
        from aiogram.webhook.aiohttp_server import setup_application
        from aiohttp import web

        await bot.set_webhook(WEBHOOK_URL)
        app = web.Application()
        setup_application(app, dp, bot=bot)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, port=PORT)
        await site.start()
        log.info(f"Webhook on :{PORT}")
        await bot.session.close()
    else:
        await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())