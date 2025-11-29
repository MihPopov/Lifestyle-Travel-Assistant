import asyncio
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv
import os
import re
import httpx
import uuid

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()
context = {}
threads = {}
active_requests = {}
server_url = os.getenv("SERVER_URL", "http://localhost:8001")

INTERESTS = ["Природа", "Музеи", "Гастрономия", "Шопинг", "Активности и спорт", "Мероприятия/концерты"]
TRAVELERS_OPTIONS = {"Да", "Нет"}
BUDGET_OPTIONS = {"Более 10 тыс. руб", "2-10 тыс. руб", "Не более 2 тыс. руб", "Без затрат", "Не имеет значения"}


class TripContext(StatesGroup):
    travelers = State()
    interests = State()
    budget = State()


class RequestForm(StatesGroup):
    waiting_for_request = State()


def interests_keyboard(selected: list[str]):
    buttons = []
    for t in INTERESTS:
        mark = "✅ " if t in selected else ""
        buttons.append([InlineKeyboardButton(
            text=f"{mark}{t}",
            callback_data=t
        )])
    buttons.append([
        InlineKeyboardButton(text="💯 Готово", callback_data="done")
    ])
    buttons.append([
        InlineKeyboardButton(text="⛔ Завершить опрос досрочно", callback_data="stop")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def markdown_to_telegram_html(text: str) -> str:
    """
    Конвертирует markdown в HTML для Telegram.
    Поддерживаемые теги: <b>, <i>, <u>, <s>, <code>, <pre>, <a>
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

    # Ссылки [text](url) -> <a href="url">text</a>
    # Разрешаем только безопасные схемы (http, https, mailto). В противном случае оставляем только текст.
    def _replace_link(m):
        link_text = m.group(1)
        url = m.group(2).strip()
        if re.match(r'^(https?://|mailto:)', url, flags=re.IGNORECASE):
            safe_url = (url.replace('&', '&amp;')
                        .replace('"', '&quot;')
                        .replace('<', '&lt;')
                        .replace('>', '&gt;'))
            return f'<a href="{safe_url}">{link_text}</a>'
        return link_text

    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', _replace_link, text)

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
async def start(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    await state.clear()
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
    current_state = await state.get_state()
    if current_state in (s.state for s in TripContext):
        await callback.message.answer("Сначала завершите опрос!")
        await callback.answer()
        return
    if current_state == RequestForm.waiting_for_request.state:
        await callback.answer()
        return
    await bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")
    await callback.message.answer("Хорошо! Напишите интересующий вас вопрос.")
    await state.set_state(RequestForm.waiting_for_request.state)
    await callback.answer()


@dp.callback_query(F.data == "yes")
async def start_questions(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state in (s.state for s in TripContext):
        await callback.answer()
        return
    await bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")
    await state.set_state(TripContext.travelers.state)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да", callback_data="Да")],
            [InlineKeyboardButton(text="Нет", callback_data="Нет")],
            [InlineKeyboardButton(text="⛔ Завершить опрос досрочно", callback_data="stop")]
        ]
    )
    msg = await callback.message.answer("*[1 / 3]* Есть ли дети в вашей компании?", reply_markup=keyboard,
                                        parse_mode="Markdown")
    await state.update_data(current_message_id=msg.message_id)
    await callback.answer()


@dp.callback_query(TripContext.travelers)
async def interests_question(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")
    if callback.data == "stop":
        await callback.message.answer("Принято! Можете задавать вопросы сейчас. Опрос можно будет пройти позже.")
        await callback.answer()
        await state.set_state(RequestForm.waiting_for_request.state)
        return
    if callback.data not in TRAVELERS_OPTIONS:
        await callback.answer()
        return
    context[callback.message.chat.id]["age"] = callback.data
    selected = []
    await state.update_data(selected_interests=selected)
    data = await state.get_data()
    msg_id = data.get("current_message_id")
    await callback.message.bot.edit_message_text(
        chat_id=callback.message.chat.id,
        message_id=msg_id,
        text="*[2 / 3]* Что вам ближе? Можно выбрать несколько или не выбирать ничего:",
        parse_mode="Markdown",
        reply_markup=interests_keyboard(selected)
    )
    await state.set_state(TripContext.interests)
    await callback.answer()


@dp.callback_query(TripContext.interests)
async def process_interests(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")
    allowed = set(INTERESTS) | {"done"}
    if callback.data == "stop":
        await callback.message.answer(
            "Принято! Можете задавать вопросы сейчас. Опрос можно будет пройти позже с помощью команды /poll.")
        await callback.answer()
        await state.set_state(RequestForm.waiting_for_request.state)
        return
    if callback.data not in allowed:
        await callback.answer()
        return
    data = await state.get_data()
    selected: list = data.get("selected_interests", [])
    value = callback.data
    if value == "done":
        await state.update_data(selected_interests=selected)
        context[callback.message.chat.id]["interests"] = selected
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Более 10 тыс. руб", callback_data="Более 10 тыс. руб")],
                [InlineKeyboardButton(text="2-10 тыс. руб", callback_data="2-10 тыс. руб")],
                [InlineKeyboardButton(text="Не более 2 тыс. руб", callback_data="Не более 2 тыс. руб")],
                [InlineKeyboardButton(text="Без затрат", callback_data="Без затрат")],
                [InlineKeyboardButton(text="Не имеет значения", callback_data="Не имеет значения")],
                [InlineKeyboardButton(text="⛔ Завершить опрос досрочно", callback_data="stop")]
            ]
        )
        msg_id = data.get("current_message_id")
        await callback.message.bot.edit_message_text(
            chat_id=callback.message.chat.id,
            message_id=msg_id,
            text="*[3 / 3]* На какой бюджет ориентируемся?",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await state.set_state(TripContext.budget)
        await callback.answer()
        return
    if value in selected:
        selected.remove(value)
    else:
        selected.append(value)
    await state.update_data(selected_interests=selected)
    await callback.message.edit_reply_markup(
        reply_markup=interests_keyboard(selected)
    )
    await callback.answer()


@dp.callback_query(TripContext.budget)
async def budget_question(callback: types.CallbackQuery, state: FSMContext):
    await bot.send_chat_action(chat_id=callback.message.chat.id, action="typing")
    if callback.data == "stop":
        await callback.message.answer("Принято! Можете задавать вопросы сейчас. Опрос можно будет пройти позже.")
        await callback.answer()
        await state.set_state(RequestForm.waiting_for_request.state)
        return
    if callback.data not in BUDGET_OPTIONS:
        await callback.answer()
        return
    context[callback.message.chat.id]["budget"] = callback.data
    await callback.message.answer(
        "Отлично! Вы ответили на все вопросы. Теперь я могу составить более "
        "персонализированные рекомендации для вас. Вы в любой момент можете пройти опрос "
        "заново командой /poll или сбросить его результаты командой /clear.",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(RequestForm.waiting_for_request.state)
    await callback.answer()


@dp.callback_query(RequestForm.waiting_for_request)
async def block_in_waiting(callback: types.CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current is None or current == RequestForm.waiting_for_request.state:
        await callback.answer()
        return


@dp.message(Command("clear"))
async def clear(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    current_state = await state.get_state()
    if current_state in (s.state for s in TripContext):
        await message.answer("Сначала завершите опрос!")
        return
    threads[message.from_user.id] = str(uuid.uuid4())
    context[message.chat.id] = {}
    await message.answer("Ваша история и ответы на вопросы, если были даны, очищены!")


@dp.message(Command("poll"))
async def start_poll(message: Message, state: FSMContext):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    current_state = await state.get_state()
    if current_state in (s.state for s in TripContext):
        await message.answer("Вы уже проходите опрос!")
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да", callback_data="Да")],
            [InlineKeyboardButton(text="Нет", callback_data="Нет")],
            [InlineKeyboardButton(text="⛔ Завершить опрос досрочно", callback_data="stop")],
        ]
    )
    msg = await message.answer("*[1 / 3]* Есть ли дети в вашей компании?", reply_markup=keyboard,
                               parse_mode="Markdown")
    await state.update_data(current_message_id=msg.message_id)
    await state.set_state(TripContext.travelers.state)


@dp.message(RequestForm.waiting_for_request)
async def agent_request(message: Message):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    chat_id = message.chat.id
    if active_requests.get(chat_id, False):
        await message.answer("⏳ Подожди, я думаю над предыдущим вопросом...")
        return
    active_requests[chat_id] = True
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    f"{server_url}/chat",
                    json={
                        "message": message.text,
                        "thread_id": threads.get(message.from_user.id),
                        "context": context.get(message.chat.id, {})
                    }
                )
                response.raise_for_status()
                data = response.json()["response"]
                await message.answer(markdown_to_telegram_html(data), parse_mode="HTML")
            except httpx.TimeoutException:
                await message.answer("Извините, запрос занял слишком много времени. Попробуйте еще раз.")
            except httpx.HTTPStatusError as e:
                await message.answer(f"Произошла ошибка при обработке запроса. Попробуйте еще раз позже.")
            except Exception as e:
                await message.answer("Произошла непредвиденная ошибка. Попробуйте еще раз позже.")
    finally:
        active_requests[chat_id] = False


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())