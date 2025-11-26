import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from dotenv import load_dotenv
import os
import uuid
import requests

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI
from langchain.tools import tool

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()
# threads = {}
# server_url = "http://localhost:8001/v1"

@tool
def add_function(a: int, b: int) -> int:
    """Складывает два числа."""
    return a + b

@tool
def mult_function(a: int, b: int) -> int:
    """Перемножает два числа."""
    return a * b

tools = [add_function, mult_function]
model = ChatOpenAI(base_url="http://localhost:8000/v1", model="Qwen/Qwen2.5-7B-Instruct", api_key="dummy")
agent = create_agent(model=model, tools=tools)
@dp.message(Command("start"))
async def cmd_start(message: Message):
    # threads[message.from_user.id] = str(uuid.uuid4())
    await message.answer("Привет! Я Lifestyle Travel Assistant.")

@dp.message(Command("clear"))
async def cmd_start(message: Message):
    # threads[message.from_user.id] = str(uuid.uuid4())
    await message.answer("История очищена")

@dp.message()
async def echo(message: Message):
    # response = requests.post(
    #     f"{server_url}/chat",
    #     json={
    #         "message": message.text,
    #         "thread_id": threads.get(message.from_user.id)
    #     },
    #     timeout=60.0
    # )
    # data = response.json()["response"]
    result = agent.invoke(
        {"messages": [{"role": "user", "content": message.text}]},
        context={"user_role": "expert"}
    )
    answer = result["messages"][-1].content
    await message.answer(answer)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())