import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from dotenv import load_dotenv
import os
import uuid
import requests
import time
import sys


load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()
threads = {}
# Используем имя сервиса из docker-compose для Docker сети
# или localhost для локального запуска
server_url = os.getenv("SERVER_URL", "http://localhost:8001")


@dp.message(Command("start"))
async def cmd_start(message: Message):
    threads[message.from_user.id] = str(uuid.uuid4())
    await message.answer("Привет! Я Lifestyle Travel Assistant.")

@dp.message(Command("clear"))
async def cmd_start(message: Message):
    threads[message.from_user.id] = str(uuid.uuid4())
    await message.answer("История очищена")

@dp.message()
async def echo(message: Message):
    try:
        response = requests.post(
            f"{server_url}/chat",
            json={
                "message": message.text,
                "thread_id": threads.get(message.from_user.id)
            },
            timeout=60.0
        )
        
        if response.status_code == 200:
            data = response.json()["response"]
            await message.answer(data)
        else:
            await message.answer(f"❌ Ошибка сервера: {response.status_code}")
            
    except requests.exceptions.Timeout:
        await message.answer("⏱️ Превышено время ожидания ответа от сервера")
    except requests.exceptions.ConnectionError:
        await message.answer("🔌 Нет связи с сервером. Попробуйте позже.")
    except Exception as e:
        await message.answer(f"❌ Произошла ошибка: {str(e)}")


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
