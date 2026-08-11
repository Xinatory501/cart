# 📋 Отчет о выполненных доработках и верификации (CartaMe Bot v1.5.6)

В данном документе подробно описано, **что было сделано**, **как это реализовано технически** и **как проверена работоспособность** каждого пункта в кодовой базе проекта.

---

## 📑 Содержание
1. [CT-P0-01: Версионированные миграции БД и автобэкапы](#1-ct-p0-01-версионированные-миграции-бд-и-автобэкапы)
2. [CT-P0-02: Криптографическое шифрование AI-ключей at-rest](#2-ct-p0-02-криптографическое-шифрование-ai-ключей-at-rest)
3. [CT-P0-03: Web API CSAT & Idempotency](#3-ct-p0-03-web-api-csat--idempotency)
4. [CT-P0-04: Авторизация Web API и защита от IDOR](#4-ct-p0-04-авторизация-web-api-и-защита-от-idor)
5. [CT-P0-05: Привязка Telegram-топика к сессии обращения](#5-ct-p0-05-привязка-telegram-топика-к-сессии-обращения)
6. [CT-P0-06: Deny-by-default авторизация и RBAC админки](#6-ct-p0-06-deny-by-default-авторизация-и-rbac-админки)
7. [CT-P0-07: Реестр регионов, профили проектов и Provisioning](#7-ct-p0-07-реестр-регионов-профили-проектов-и-provisioning)
8. [CT-P0-08: Доменные адаптеры лояльности (NIVEA, SQB) и Bitrix24](#8-ct-p0-08-доменные-адаптеры-лояльности-nivea-sqb-и-bitrix24)
9. [📱 Обязательная верификация номера телефона при старте](#9--обязательная-верификация-номера-телефона-при-старте)
10. [🧪 Результаты тестирования и верификации](#10--результаты-тестирования-и-верификации)

---

## 1. CT-P0-01: Версионированные миграции БД и автобэкапы

### Что сделано:
- Отказались от небезопасного `metadata.create_all()`.
- Внедрен полноценный стек миграций на базе **Alembic** с поддержкой как SQLite, так и PostgreSQL (`asyncpg`).
- Реализовано автоматическое создание резервной копии базы данных перед применением миграций в папку `data/backups/bot.db.backup_<timestamp>`.
- Схема миграций сделана условной (Conditional) — существующие таблицы и столбцы инспектируются через `sa.inspect()`, что исключает ошибки при накатывании на живую БД.

### Как реализовано:
- **Файлы**: `alembic.ini`, `migrations/env.py`, `migrations/versions/2026_08_10_1335-7a47994329ec_initial_schema.py`, `migrations/versions/2026_08_11_2115-b1298461cd12_add_user_phone_number.py`.
- **Точка входа**: В `database/database.py` метод `init_db()` запускает `alembic.command.upgrade(alembic_cfg, "head")` внутри изолированного `ThreadPoolExecutor`, предотвращая конфликт асинхронных циклов событий (`asyncio.run()`).

---

## 2. CT-P0-02: Криптографическое шифрование AI-ключей at-rest

### Что сделано:
- Устранена уязвимость сохранения незашифрованных API-ключей провайдеров в базу данных.
- Все ключи шифруются симметричным шифрованием (AES/Fernet) или через HashiCorp Vault Transit Engine перед сохранением в БД.
- Добавлена автоматическая фоновая миграция существующих plaintext-ключей в зашифрованный формат с префиксом `enc:` / `vault:`.
- В пользовательском интерфейсе и логах ключи маскируются (`sk-te...3456`).

### Как реализовано:
- **Файлы**: `utils/encryption.py`, `database/repository.py` (`APIKeyRepository`), `services/ai_service.py`.
- Метод `APIKeyRepository.normalize_api_key()` очищает пробелы, кавычки и префиксы `Bearer `, а `create()` шифрует значение вызовом `encrypt_value()`.
- Расшифровка ключа происходит исключительно на лету в `AIService._effective_api_key()` непосредственно перед обращением к OpenAI/Router API.

---

## 3. CT-P0-03: Web API CSAT & Idempotency

### Что сделано:
- Устранены ошибки рантайма (NameError `asyncio`) в обработчиках веб-сервера.
- Схема CSAT-отзывов приведена в полное соответствие с контрактом OpenAPI (`rating` [1..5] и текстовый `comment`).
- Добавлена проверка статуса сессии: отзыв принимается только для завершенных/решенных обращений (`RESOLVED` или `CLOSED`).
- Реализована идемпотентность: повторный отзыв по одной сессии обновляет оценку, не создавая дубликатов.

### Как реализовано:
- **Файлы**: `services/web_server.py`, `database/repository.py` (`ChatRepository.get_session`).
- Эндпоинт `POST /api/v1/feedback` извлекает `session_id`, валидирует статус обращения и сохраняет оценку через `ChatRepository.save_csat()`.

---

## 4. CT-P0-04: Авторизация Web API и защита от IDOR

### Что сделано:
- Запрещен детерминированный мастер-токен по умолчанию.
- Реализован менеджер криптографических сессионных токенов `SessionTokenManager` на базе HMAC-SHA256.
- Закрыта уязвимость IDOR: клиент с сессионным токеном имеет доступ **только** к сообщениям и действиям своей собственной сессии.
- Добавлен глобальный `cors_middleware` с корректной обработкой preflight OPTIONS-запросов.

### Как реализовано:
- **Файлы**: `services/web_server.py`.
- При открытии веб-сессии генерируется подписанный токен `SessionTokenManager.generate_token(user_id, session_id, secret)`.
- Middleware `auth_middleware` валидирует подпись и сверяет `payload["session_id"] == requested_session_id`.

---

## 5. CT-P0-05: Привязка Telegram-топика к сессии обращения

### Что сделано:
- Исправлена проблема пустых `support_thread_id` в таблице `chat_sessions`.
- Теперь при создании кейса и привязки темы на форуме поддержки `support_thread_id` сразу сохраняется в активную модель `ChatSession`.
- Команды операторов поддержки (`/claim`, `/unclaim`, `/resolve`, `/status`, `/hint`) безошибочно находят текущее обращение по `message_thread_id`.

### Как реализовано:
- **Файлы**: `services/thread_service.py`, `handlers/menu.py`, `database/repository.py` (`ChatRepository.create_session`).
- Метод `ThreadService._save_thread_mapping()` обновляет `active_session.support_thread_id = thread_id`.

---

## 6. CT-P0-06: Deny-by-default авторизация и RBAC админки

### Что сделано:
- Переработан `AdminAuthMiddleware`: теперь он проверяет не только `CallbackQuery`, но и `Message`, и состояния FSM.
- Реализована строгая модель RBAC (`superadmin`, `project_admin`, `supervisor`, `operator`, `user`).
- Роль `project_admin` ограничена от опасных операций (выгрузка дампа БД, изменение системных API-ключей и антифлуда).
- Все попытки доступа (успешные и заблокированные) логируются в неизменяемую таблицу `admin_actions`.

### Как реализовано:
- **Файлы**: `middlewares/admin_auth.py`, `bot.py`.
- Middleware зарегистрирован на события `dp.message` и `dp.callback_query`.

---

## 7. CT-P0-07: Реестр регионов, профили проектов и Provisioning

### Что сделано:
- Созданы таблицы `regions`, `project_profiles`, `bot_instances`, `provisioning_events`.
- Инициализирован базовый каталог регионов (`BY`, `KZ`, `UZ`) и профилей проектов (`BUSINESS`, `BANK`).
- Каталог для `UZ` поддерживает режим `BANK` для банковских интеграций (SQB).
- Создан `ProvisioningService` с поддержкой жизненного цикла инстансов (`create`, `activate`, `suspend`).

### Как реализовано:
- **Файлы**: `database/models.py`, `services/provisioning_service.py`, `database/database.py`.

---

## 8. CT-P0-08: Доменные адаптеры лояльности (NIVEA, SQB) и Bitrix24

### Что сделано:
- Реализован адаптер лояльности NIVEA KZ: проверка статуса участника, баланс баллов, каталог акций, регистрация чеков и купонов.
- Реализован банковский адаптер SQB UZ: проверка согласий, привязка Mastercard, баланс бонусов, выписка операций.
- В SQB-адаптере внедрено строгое маскирование номеров карт (PAN) и категорический запрет на передачу/логирование CVV, PIN и OTP.
- Реализован адаптер Bitrix24: создание и обновление задач техподдержки L2/L3 при эскалациях.

### Как реализовано:
- **Файлы**: `adapters/nivea_adapter.py`, `adapters/sqb_adapter.py`, `adapters/bitrix24_adapter.py`.

---

## 9. 📱 Обязательная верификация номера телефона при старте

### Что сделано:
- При первом запуске `/start` (после выбора языка и политики конфиденциальности) бот запрашивает подтверждение номера телефона.
- Пользователь **не может пройти дальше** в меню и чат, пока не подтвердит номер.
- Предоставляется специальная кнопка Telegram: `📱 Поделиться номером телефона` (`request_contact=True`).
- **Антиспуфинг / Защита от подделки**: бот проверяет, что контакт принадлежит именно отправителю (`message.contact.user_id == message.from_user.id`). Попытка отправить чужой контакт блокируется.
- Номер сохраняется в базе данных в поле `users.phone_number`.
- Номер отображается в первом сообщении при создании топика поддержки и в карточке пользователя в панели администратора.
- Добавлены локализации на 5 языков (`ru`, `en`, `uz`, `kk`, `kz`).

### Как реализовано:
- **Файлы**: `handlers/start.py`, `keyboards/menu.py`, `states/user_states.py` (`UserStates.sharing_phone`), `database/models.py`, `database/repository.py`, `services/thread_service.py`, `handlers/admin/user_management.py`, `locales/*.json`.

---

## 10. 🧪 Результаты тестирования и верификации

### 1. Автоматические тесты (Pytest)
Запуск набора юнит-тестов:
```bash
python3 -m pytest tests/ -v
```
**Результат:**
```text
tests/test_p0_fixes.py::test_sqb_card_masking PASSED                     [ 14%]
tests/test_p0_fixes.py::test_session_token_manager PASSED                [ 28%]
tests/test_p0_fixes.py::test_api_key_normalization PASSED                [ 42%]
tests/test_p0_fixes.py::test_encryption_decryption PASSED                [ 57%]
tests/test_phone_number.py::test_phone_request_keyboard PASSED           [ 71%]
tests/test_phone_number.py::test_contact_ownership_verification PASSED   [ 85%]
tests/test_phone_number.py::test_user_phone_number_update PASSED         [100%]

========================= 7 passed, 1 warning in 3.23s =========================
```

### 2. Проверка схемы базы данных SQLite (`data/cartame_bot.db`)
- **Все 20 таблиц присутствуют в БД**:
  `users`, `config`, `training_messages`, `ai_providers`, `chat_sessions`, `flood_log`, `admin_actions`, `metrics`, `api_keys`, `ai_models`, `case_events`, `csat_responses`, `chat_history`, `pending_requests`, `clarification_contexts`, `alembic_version`, `regions`, `project_profiles`, `bot_instances`, `provisioning_events`.
- Поле `phone_number` присутствует в таблице `users`.
- Поля `support_thread_id`, `ticket_code`, `sla_first_response_deadline` присутствуют в `chat_sessions`.
- Регионы `BY`, `KZ`, `UZ` инициализированы в таблице `regions`.
- Текущая ревизия Alembic: `b1298461cd12` (Head).
