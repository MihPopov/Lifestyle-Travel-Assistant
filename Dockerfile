# Используем официальный Python образ
FROM python:3.12-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем зависимости системы (если нужно)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Копируем файлы проекта
COPY . .

# Устанавливаем python-зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Указываем переменные окружения (dotenv загрузит их)
ENV PYTHONUNBUFFERED=1

# Команда запуска бота
CMD ["python", "bot.py"]