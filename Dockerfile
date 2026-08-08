# ============================================================
# CartaMe Bot — Dockerfile
# Python 3.12-slim: поддержка X|Y type hints, ARM64 (M4)
# ============================================================
FROM python:3.12-slim

# Системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Зависимости в отдельном слое (кэш)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Исходный код
COPY . .

# Папка для SQLite базы данных
RUN mkdir -p /app/data

# Запуск от непривилегированного пользователя
RUN useradd -m -u 1001 botuser && chown -R botuser:botuser /app
USER botuser

CMD ["python", "bot.py"]
