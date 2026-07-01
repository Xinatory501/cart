FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Копируем requirements
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код
COPY . .

# Создаем директорию для БД если её нет
RUN mkdir -p /app/data

# Запуск бота
CMD ["python", "bot.py"]
