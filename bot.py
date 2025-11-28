import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv
import os
import re
import requests
import uuid

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()
context = {}
threads = {}
server_url = os.getenv("SERVER_URL", "http://localhost:8001/v1")

INTERESTS = ["Природа", "Музеи", "Гастрономия", "Шопинг", "Активности и спорт", "Мероприятия/концерты"]
TRAVELERS_OPTIONS = {"Один", "Пара", "Семья с детьми", "Друзья"}
AGE_KIDS_OPTIONS = {"0-4 года", "5-10 лет", "11-17 лет"}
AGE_ADULT_OPTIONS = {"18-25 лет", "26-35 лет", "36-47 лет", "48-59 лет", "60+ лет"}
PLAN_STYLE_OPTIONS = {"Спокойный", "Активный"}
BUDGET_OPTIONS = {
    "Более 10 тыс. руб", "2-10 тыс. руб", "Не более 2 тыс. руб", "Без затрат", "Не имеет значения"
}

class TripContext(StatesGroup):
    travelers = State()
    age = State()
    interests = State()
    plan_style = State()
    budget = State()


class RequestForm(StatesGroup):
    waiting_for_request = State()

def interests_keyboard(selected: set[str]):
    buttons = []
    for t in INTERESTS:
        mark = "✔ " if t in selected else ""
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{t}",
            callback_data=t
        )])
    buttons.append([
        InlineKeyboardButton(text="Готово", callback_data="done")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def markdown_to_telegram_html(text: str) -> str:
    """
    Конвертирует markdown в HTML для Telegram.
    Поддерживаемые теги: <b>, <i>, <u>, <s>, <code>, <pre>
    Неподдерживаемое: удаляется
    """

    # Экранируем HTML-символы
    text = (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            )

    # Обрабатываем код-блоки (```code```) -> <pre>code</pre>
    text = re.sub(r'```(\w+)?\n?(.*?)```', r'<pre>\2</pre>', text, flags=re.DOTALL)

    # Обрабатываем инлайн-код (`code`) -> <code>code</code>
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

    # Жирный текст: **text** или __text__ -> <b>text</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.*?)__', r'<b>\1</b>', text)

    # Курсив: *text* или _text_ -> <i>text</i>
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'_(.*?)_', r'<i>\1</i>', text)

    # Подчеркивание: ++text++ -> <u>text</u> (нестандартный синтаксис, но иногда используется)
    text = re.sub(r'\+\+(.*?)\+\+', r'<u>\1</u>', text)

    # Зачеркивание: ~~text~~ -> <s>text</s>
    text = re.sub(r'~~(.*?)~~', r'<s>\1</s>', text)

    # Удаляем неподдерживаемые элементы:
    # Заголовки (# Header) -> просто текст
    text = re.sub(r'#+\s*(.*)', r'\1', text)

    # Ссылки [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Изображения ![alt](url) -> удаляем
    text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', '', text)

    # Цитаты (> quote) -> просто текст
    text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)

    # Удаляем оставшиеся markdown символы
    text = re.sub(r'[*_~`\[\]]', '', text)

    # Очищаем лишние переносы строк
    text = re.sub(r'\n\s*\n', '\n\n', text)

    return text.strip()

@dp.message(Command("start"))
async def start(message: Message):
    context[message.chat.id] = {}
    threads[message.from_user.id] = str(uuid.uuid4())
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, я готов(а) ответить на вопросы", callback_data="yes")],
            [InlineKeyboardButton(text="Нет, давай сразу к делу", callback_data="no")]
        ]
    )
    await message.answer(
        "Привет! Я умею искать мероприятия, заведения и узнавать погоду. Например, "
        "я могу найти концерт в Москве, кафе в Адлере или рассказать о погоде в Сочи. "
        "Но перед этим хочу задать пару вопросов, чтобы составлять наиболее качественные рекомендации. "
        "Вы не будете против?",
        reply_markup=keyboard
    )

@dp.callback_query(F.data == "no")
async def just_answer(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Хорошо! Напишите интересующий вас вопрос.")
    await state.set_state(RequestForm.waiting_for_request.state)
    await callback.answer()

@dp.callback_query(F.data == "yes")
async def start_questions(callback: types.CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Один", callback_data="Один")],
            [InlineKeyboardButton(text="Пара", callback_data="Пара")],
            [InlineKeyboardButton(text="Семья с детьми", callback_data="Семья с детьми")],
            [InlineKeyboardButton(text="Друзья", callback_data="Друзья")]
        ]
    )
    await callback.message.answer("Кто путешествует?", reply_markup=keyboard)
    await state.set_state(TripContext.travelers.state)
    await callback.answer()

@dp.callback_query(TripContext.travelers)
async def age_question(callback: types.CallbackQuery, state: FSMContext):
    if callback.data not in TRAVELERS_OPTIONS:
        await callback.answer()
        return
    await state.update_data(travelers=callback.data)
    context[callback.message.chat.id]["travelers"] = callback.data
    if callback.data == "Семья с детьми":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="0-4 года", callback_data="0-4 года")],
                [InlineKeyboardButton(text="5-10 лет", callback_data="5-10 лет")],
                [InlineKeyboardButton(text="11-17 лет", callback_data="11-17 лет")]
            ]
        )
        await callback.message.answer("Какого возраста дети?", reply_markup=keyboard)
    elif callback.data in ["Один", "Пара", "Друзья"]:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="18-25 лет", callback_data="18-25 лет")],
                [InlineKeyboardButton(text="26-35 лет", callback_data="26-35 лет")],
                [InlineKeyboardButton(text="36-47 лет", callback_data="36-47 лет")],
                [InlineKeyboardButton(text="48-59 лет", callback_data="48-59 лет")],
                [InlineKeyboardButton(text="60+ лет", callback_data="60+ лет")]
            ]
        )
        await callback.message.answer("Каков средний возраст компании?", reply_markup=keyboard)
    await state.set_state(TripContext.age.state)
    await callback.answer()

@dp.callback_query(TripContext.age)
async def interests_question(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if data["travelers"] == "Семья с детьми":
        allowed = AGE_KIDS_OPTIONS
    else:
        allowed = AGE_ADULT_OPTIONS
    if callback.data not in allowed:
        await callback.answer()
        return
    await state.update_data(age=callback.data)
    context[callback.message.chat.id]["age"] = callback.data
    selected = set()
    await state.update_data(selected_interests=selected)
    await callback.message.answer(
        "Что вам ближе? Можно выбрать несколько или не выбирать ничего:",
        reply_markup=interests_keyboard(selected)
    )
    await state.set_state(TripContext.interests)
    await callback.answer()

@dp.callback_query(TripContext.interests)
async def process_interests(callback: types.CallbackQuery, state: FSMContext):
    allowed = set(INTERESTS) | {"done"}
    if callback.data not in allowed:
        await callback.answer()
        return
    data = await state.get_data()
    selected: set = set(data.get("selected_interests", []))
    value = callback.data
    if value == "done":
        await state.update_data(selected_interests=selected)
        context[callback.message.chat.id]["interests"] = selected
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Спокойный", callback_data="Спокойный")],
                [InlineKeyboardButton(text="Активный", callback_data="Активный")]
            ]
        )
        await callback.message.answer("Какой формат отдыха вам ближе?", reply_markup=keyboard)
        await state.set_state(TripContext.plan_style)
        await callback.answer()
        return
    if value in selected:
        selected.remove(value)
    else:
        selected.add(value)
    await state.update_data(selected_interests=selected)
    await callback.message.edit_reply_markup(
        reply_markup=interests_keyboard(selected)
    )
    await callback.answer()

@dp.callback_query(TripContext.plan_style)
async def budget_question(callback: types.CallbackQuery, state: FSMContext):
    if callback.data not in PLAN_STYLE_OPTIONS:
        await callback.answer()
        return
    await state.update_data(plan_style=callback.data)
    context[callback.message.chat.id]["plan_style"] = callback.data
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Более 10 тыс. руб", callback_data="Более 10 тыс. руб")],
            [InlineKeyboardButton(text="2-10 тыс. руб", callback_data="2-10 тыс. руб")],
            [InlineKeyboardButton(text="Не более 2 тыс. руб", callback_data="Не более 2 тыс. руб")],
            [InlineKeyboardButton(text="Без затрат", callback_data="Без затрат")],
            [InlineKeyboardButton(text="Не имеет значения", callback_data="Не имеет значения")]
        ]
    )
    await callback.message.answer("На какой бюджет ориентируемся?", reply_markup=keyboard)
    await state.set_state(TripContext.budget)
    await callback.answer()

@dp.callback_query(TripContext.budget)
async def budget_question(callback: types.CallbackQuery, state: FSMContext):
    if callback.data not in BUDGET_OPTIONS:
        await callback.answer()
        return
    await state.update_data(budget=callback.data)
    context[callback.message.chat.id]["budget"] = callback.data
    await callback.message.answer(
        "Отлично! Вы ответили на все вопросы. Теперь я могу составить более "
        "персонализированные рекомендации для вас. Вы в любой момент можете пройти опрос "
        "заново или сбросить его результаты командой \clear.")
    await state.set_state(RequestForm.waiting_for_request.state)
    await callback.answer()

@dp.callback_query(RequestForm.waiting_for_request)
async def block_in_waiting(callback: types.CallbackQuery):
    await callback.answer()

@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    threads[message.from_user.id] = str(uuid.uuid4())
    context[message.chat.id] = {}
    await message.answer("Ваша история и ответы на вопросы, если были даны, очищены!")

@dp.message(RequestForm.waiting_for_request)
async def echo(message: Message):
    response = requests.post(
        f"{server_url}/chat",
        json={
            "message": message.text,
            "thread_id": threads.get(message.from_user.id),
            "context": context[message.chat.id]
        },
        timeout=60.0
    )
    data = response.json()["response"]
    await message.answer(markdown_to_telegram_html(data), parse_mode="HTML")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())