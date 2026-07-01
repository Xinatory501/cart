import re
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext

from database.database import get_session
from database.repository import AIProviderRepository, APIKeyRepository, AIModelRepository, AdminRepository
from states.admin_states import AdminStates

router = Router()


def _normalize_provider_name(display_name: str) -> str:
    slug = display_name.strip().lower()
    slug = slug.replace(" ", "_")
    slug = re.sub(r"[^a-z0-9_]+", "", slug)
    return slug or "custom_provider"

@router.callback_query(F.data == "admin_api_keys")
async def show_providers_list(callback: CallbackQuery):
    async with get_session() as session:
        ai_provider_repo = AIProviderRepository(session)
        providers = await ai_provider_repo.get_all()

    text = "🔑 <b>Управление AI провайдерами</b>\n\n"

    if providers:
        text += "Выберите провайдера для управления ключами:\n\n"
        for provider in providers:
            status = "✅" if provider.is_active else "❌"
            default = " 🌟" if provider.is_default else ""
            text += f"{status} <b>{provider.display_name}</b>{default}\n\n"
    else:
        text += "Нет настроенных провайдеров.\n"

    keyboard = []

    for provider in providers:
        keyboard.append([InlineKeyboardButton(
            text=f"🔧 {provider.display_name}",
            callback_data=f"provider_{provider.id}"
        )])

    keyboard.append([InlineKeyboardButton(
        text="➕ Добавить провайдера",
        callback_data="add_provider"
    )])

    keyboard.append([InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="admin_menu"
    )])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "add_provider")
async def add_provider_menu(callback: CallbackQuery):
    text = (
        "➕ <b>Добавление провайдера</b>\n\n"
        "Выберите тип провайдера:\n"
        "• Локальный (Ollama/LM Studio/OpenAI-compatible API)\n"
        "• Внешний (облачный API с ключом)\n\n"
        "Добавление сделано пошаговым мастером."
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Локальный", callback_data="add_provider_local")],
        [InlineKeyboardButton(text="☁️ Внешний", callback_data="add_provider_remote")],
        [InlineKeyboardButton(text="📘 Инструкция (локальный)", callback_data="local_provider_instruction")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="admin_api_keys")],
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


def _back_keyboard(callback_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=callback_data)]]
    )


@router.callback_query(F.data == "local_provider_instruction")
async def local_provider_instruction(callback: CallbackQuery):
    text = (
        "📘 <b>Как добавить локального провайдера</b>\n\n"
        "<b>1.</b> Поднимите локальный OpenAI-compatible endpoint.\n"
        "Примеры:\n"
        "• Ollama: <code>http://127.0.0.1:11434/v1</code>\n"
        "• LM Studio: <code>http://127.0.0.1:1234/v1</code>\n"
        "Если бот в Docker, обычно нужен адрес хоста:\n"
        "• <code>http://host.docker.internal:11434/v1</code>\n\n"
        "<b>2.</b> В админке нажмите <b>Добавить провайдера → Локальный</b>.\n"
        "<b>3.</b> Пройдите 3 шага мастера: имя → URL → модель.\n\n"
        "Пример модели для Ollama: <code>llama3.1:8b</code>\n"
        "Для локального провайдера API-ключ не нужен."
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Начать добавление", callback_data="add_provider_local")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="add_provider")],
    ])

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "add_provider_local")
async def start_local_provider_wizard(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.entering_local_provider_name)

    await callback.message.answer(
        "🏠 <b>Локальный провайдер</b>\n"
        "Шаг 1/3: отправьте отображаемое имя провайдера.\n\n"
        "Пример: <code>Ollama Local</code>",
        parse_mode="HTML",
        reply_markup=_back_keyboard("add_provider"),
    )
    await callback.answer()


@router.callback_query(F.data == "provider_local_back_to_name")
async def local_back_to_name(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_local_provider_name)
    await callback.message.edit_text(
        "🏠 <b>Локальный провайдер</b>\n"
        "Шаг 1/3: отправьте отображаемое имя провайдера.",
        parse_mode="HTML",
        reply_markup=_back_keyboard("add_provider"),
    )
    await callback.answer()


@router.callback_query(F.data == "provider_local_back_to_base")
async def local_back_to_base(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_local_provider_base_url)
    await callback.message.edit_text(
        "🏠 <b>Локальный провайдер</b>\n"
        "Шаг 2/3: отправьте base_url (http://.../v1).",
        parse_mode="HTML",
        reply_markup=_back_keyboard("provider_local_back_to_name"),
    )
    await callback.answer()


@router.message(AdminStates.entering_local_provider_name)
async def local_provider_name_step(message: Message, state: FSMContext):
    display_name = message.text.strip()
    if len(display_name) < 2:
        await message.answer(
            "❌ Имя слишком короткое. Введите нормальное название.",
            reply_markup=_back_keyboard("add_provider"),
        )
        return

    await state.update_data(local_display_name=display_name)
    await state.set_state(AdminStates.entering_local_provider_base_url)

    await message.answer(
        "🏠 <b>Локальный провайдер</b>\n"
        "Шаг 2/3: отправьте base_url.\n\n"
        "Примеры:\n"
        "<code>http://127.0.0.1:11434/v1</code>\n"
        "<code>http://host.docker.internal:11434/v1</code>",
        parse_mode="HTML",
        reply_markup=_back_keyboard("provider_local_back_to_name"),
    )


@router.message(AdminStates.entering_local_provider_base_url)
async def local_provider_base_step(message: Message, state: FSMContext):
    base_url = message.text.strip()
    if not base_url.startswith(("http://", "https://")):
        await message.answer(
            "❌ base_url должен начинаться с http:// или https://",
            reply_markup=_back_keyboard("provider_local_back_to_name"),
        )
        return

    await state.update_data(local_base_url=base_url)
    await state.set_state(AdminStates.entering_local_provider_model)

    await message.answer(
        "🏠 <b>Локальный провайдер</b>\n"
        "Шаг 3/3: отправьте имя модели.\n\n"
        "Пример: <code>llama3.1:8b</code>",
        parse_mode="HTML",
        reply_markup=_back_keyboard("provider_local_back_to_base"),
    )


@router.message(AdminStates.entering_local_provider_model)
async def local_provider_model_step(message: Message, state: FSMContext):
    model_name = message.text.strip()
    if not model_name:
        await message.answer(
            "❌ Имя модели не может быть пустым",
            reply_markup=_back_keyboard("provider_local_back_to_base"),
        )
        return

    data = await state.get_data()
    display_name = data.get("local_display_name")
    base_url = data.get("local_base_url")

    provider_name = _normalize_provider_name(display_name)

    async with get_session() as session:
        ai_provider_repo = AIProviderRepository(session)
        api_key_repo = APIKeyRepository(session)
        model_repo = AIModelRepository(session)
        admin_repo = AdminRepository(session)

        provider = await ai_provider_repo.create(
            name=provider_name,
            display_name=display_name,
            base_url=base_url,
            is_default=False,
        )

        await api_key_repo.create(
            provider_id=provider.id,
            api_key="local-no-key",
            name="Local (no auth)",
        )

        await model_repo.create(
            provider_id=provider.id,
            model_name=model_name,
            display_name=model_name,
            is_default=True,
        )

        await admin_repo.log_action(
            message.from_user.id,
            "add_local_provider",
            details=f"Provider: {display_name}, URL: {base_url}, Model: {model_name}",
        )

    await state.clear()
    await message.answer(
        f"✅ Локальный провайдер <b>{display_name}</b> добавлен.\n"
        f"Модель: <code>{model_name}</code>\n\n"
        "Если нужно, сделайте его основным в карточке провайдера.",
        parse_mode="HTML",
        reply_markup=_back_keyboard("admin_api_keys"),
    )


@router.callback_query(F.data == "add_provider_remote")
async def start_remote_provider_wizard(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(AdminStates.entering_remote_provider_name)

    await callback.message.answer(
        "☁️ <b>Внешний провайдер</b>\n"
        "Шаг 1/4: отправьте отображаемое имя провайдера.\n\n"
        "Пример: <code>OpenAI Prod</code>",
        parse_mode="HTML",
        reply_markup=_back_keyboard("add_provider"),
    )
    await callback.answer()


@router.callback_query(F.data == "provider_remote_back_to_name")
async def remote_back_to_name(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_remote_provider_name)
    await callback.message.edit_text(
        "☁️ <b>Внешний провайдер</b>\n"
        "Шаг 1/4: отправьте отображаемое имя провайдера.",
        parse_mode="HTML",
        reply_markup=_back_keyboard("add_provider"),
    )
    await callback.answer()


@router.callback_query(F.data == "provider_remote_back_to_base")
async def remote_back_to_base(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_remote_provider_base_url)
    await callback.message.edit_text(
        "☁️ <b>Внешний провайдер</b>\n"
        "Шаг 2/4: отправьте base_url или '-' для официального OpenAI.",
        parse_mode="HTML",
        reply_markup=_back_keyboard("provider_remote_back_to_name"),
    )
    await callback.answer()


@router.callback_query(F.data == "provider_remote_back_to_api")
async def remote_back_to_api(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.entering_remote_provider_api_key)
    await callback.message.edit_text(
        "☁️ <b>Внешний провайдер</b>\n"
        "Шаг 3/4: отправьте API-ключ.",
        parse_mode="HTML",
        reply_markup=_back_keyboard("provider_remote_back_to_base"),
    )
    await callback.answer()


@router.message(AdminStates.entering_remote_provider_name)
async def remote_provider_name_step(message: Message, state: FSMContext):
    display_name = message.text.strip()
    if len(display_name) < 2:
        await message.answer(
            "❌ Имя слишком короткое.",
            reply_markup=_back_keyboard("add_provider"),
        )
        return

    await state.update_data(remote_display_name=display_name)
    await state.set_state(AdminStates.entering_remote_provider_base_url)

    await message.answer(
        "☁️ <b>Внешний провайдер</b>\n"
        "Шаг 2/4: отправьте base_url или <code>-</code>.\n\n"
        "Пример: <code>https://api.groq.com/openai/v1</code>",
        parse_mode="HTML",
        reply_markup=_back_keyboard("provider_remote_back_to_name"),
    )


@router.message(AdminStates.entering_remote_provider_base_url)
async def remote_provider_base_step(message: Message, state: FSMContext):
    base_url_raw = message.text.strip()
    if base_url_raw not in {"-", "none", "null"} and not base_url_raw.startswith(("http://", "https://")):
        await message.answer(
            "❌ base_url должен начинаться с http:// или https:// (или используйте '-')",
            reply_markup=_back_keyboard("provider_remote_back_to_name"),
        )
        return

    normalized_base_url = None if base_url_raw in {"-", "none", "null"} else base_url_raw
    await state.update_data(remote_base_url=normalized_base_url)
    await state.set_state(AdminStates.entering_remote_provider_api_key)

    await message.answer(
        "☁️ <b>Внешний провайдер</b>\n"
        "Шаг 3/4: отправьте API-ключ.",
        parse_mode="HTML",
        reply_markup=_back_keyboard("provider_remote_back_to_base"),
    )


@router.message(AdminStates.entering_remote_provider_api_key)
async def remote_provider_api_key_step(message: Message, state: FSMContext):
    api_key = message.text.strip()
    if not api_key:
        await message.answer(
            "❌ API-ключ не может быть пустым",
            reply_markup=_back_keyboard("provider_remote_back_to_base"),
        )
        return

    await state.update_data(remote_api_key=api_key)
    await state.set_state(AdminStates.entering_remote_provider_model)

    await message.answer(
        "☁️ <b>Внешний провайдер</b>\n"
        "Шаг 4/4: отправьте имя модели.\n\n"
        "Пример: <code>gpt-4o-mini</code>",
        parse_mode="HTML",
        reply_markup=_back_keyboard("provider_remote_back_to_api"),
    )


@router.message(AdminStates.entering_remote_provider_model)
async def remote_provider_model_step(message: Message, state: FSMContext):
    model_name = message.text.strip()
    if not model_name:
        await message.answer(
            "❌ Имя модели не может быть пустым",
            reply_markup=_back_keyboard("provider_remote_back_to_api"),
        )
        return

    data = await state.get_data()
    display_name = data.get("remote_display_name")
    base_url = data.get("remote_base_url")
    api_key = data.get("remote_api_key")

    provider_name = _normalize_provider_name(display_name)

    async with get_session() as session:
        ai_provider_repo = AIProviderRepository(session)
        api_key_repo = APIKeyRepository(session)
        model_repo = AIModelRepository(session)
        admin_repo = AdminRepository(session)

        provider = await ai_provider_repo.create(
            name=provider_name,
            display_name=display_name,
            base_url=base_url,
            is_default=False,
        )

        await api_key_repo.create(
            provider_id=provider.id,
            api_key=api_key,
            name="Main key",
        )

        await model_repo.create(
            provider_id=provider.id,
            model_name=model_name,
            display_name=model_name,
            is_default=True,
        )

        await admin_repo.log_action(
            message.from_user.id,
            "add_remote_provider",
            details=f"Provider: {display_name}, URL: {base_url}, Model: {model_name}",
        )

    await state.clear()
    await message.answer(
        f"✅ Внешний провайдер <b>{display_name}</b> добавлен.\n"
        f"Модель: <code>{model_name}</code>",
        parse_mode="HTML",
        reply_markup=_back_keyboard("admin_api_keys"),
    )


@router.callback_query(F.data.startswith("provider_"))
async def show_provider_detail(callback: CallbackQuery):
    provider_id = int(callback.data.split("_")[1])

    async with get_session() as session:
        ai_provider_repo = AIProviderRepository(session)
        api_key_repo = APIKeyRepository(session)
        model_repo = AIModelRepository(session)

        provider = await ai_provider_repo.get_by_id(provider_id)
        if not provider:
            await callback.answer("❌ Провайдер не найден", show_alert=True)
            return

        api_keys = await api_key_repo.get_by_provider(provider_id)
        models = await model_repo.get_by_provider(provider_id)

    text = f"🔧 <b>{provider.display_name}</b>\n\n"
    text += f"<b>Статус:</b> {'✅ Активен' if provider.is_active else '❌ Неактивен'}\n"
    text += f"<b>По умолчанию:</b> {'Да 🌟' if provider.is_default else 'Нет'}\n\n"

    text += f"<b>API Ключи ({len(api_keys)}):</b>\n\n"

    if api_keys:
        for i, key in enumerate(api_keys, 1):
            status = "✅" if key.is_active else "❌"
            name = key.name or f"Ключ {key.id}"
            text += f"{status} {i}. {name}\n"

            if key.requests_limit:
                text += f"   Использовано: {key.requests_made}/{key.requests_limit}\n"
            else:
                text += f"   Использовано: {key.requests_made} (безлимит)\n"

            if key.last_error:
                text += f"   ⚠️ Ошибка: {key.last_error[:50]}...\n"
            text += "\n"
    else:
        text += "Нет ключей. Добавьте хотя бы один ключ.\n"

    text += f"\n<b>Модели ({len(models)}):</b>\n"
    if models:
        for i, model in enumerate(models, 1):
            status = "✅" if model.is_active else "❌"
            default = "🌟" if model.is_default else ""
            name = model.display_name or model.model_name
            text += f"{status} {i}. {name} {default}\n"
    else:
        text += "Нет моделей. Добавьте хотя бы одну модель.\n"

    keyboard = [
        [InlineKeyboardButton(
            text="➕ Добавить ключ",
            callback_data=f"add_key_{provider_id}"
        )],
        [InlineKeyboardButton(
            text="📋 Список ключей",
            callback_data=f"list_keys_{provider_id}"
        )],
        [InlineKeyboardButton(
            text="🎯 Управление моделями",
            callback_data=f"manage_models_{provider_id}"
        )],
        [InlineKeyboardButton(
            text="🔄 Сделать основным" if not provider.is_default else "✅ Основной",
            callback_data=f"set_default_{provider_id}"
        )],
        [InlineKeyboardButton(
            text="🗑 Удалить провайдера",
            callback_data=f"delete_provider_{provider_id}"
        )],
        [InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data="admin_api_keys"
        )]
    ]

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("add_key_"))
async def request_add_key(callback: CallbackQuery, state: FSMContext):
    provider_id = int(callback.data.split("_")[2])

    await state.update_data(provider_id=provider_id)
    await state.set_state(AdminStates.entering_api_key)

    await callback.message.answer(
        "🔑 Отправьте новый API ключ для этого провайдера:\n\n"
        "Также можете указать название через запятую:\n"
        "Пример: sk-xxxx, Основной ключ"
    )
    await callback.answer()

@router.message(AdminStates.entering_api_key)
async def save_new_key(message: Message, state: FSMContext):
    data = await state.get_data()
    provider_id = data.get("provider_id")

    parts = message.text.split(",", 1)
    api_key = parts[0].strip()
    name = parts[1].strip() if len(parts) > 1 else None

    async with get_session() as session:
        api_key_repo = APIKeyRepository(session)
        admin_repo = AdminRepository(session)

        await api_key_repo.create(
            provider_id=provider_id,
            api_key=api_key,
            name=name
        )

        await admin_repo.log_action(
            message.from_user.id,
            "add_api_key",
            details=f"Provider ID: {provider_id}, Name: {name or 'No name'}"
        )

    await message.answer(f"✅ API ключ добавлен!\nНазвание: {name or 'Без названия'}")
    await state.clear()

@router.callback_query(F.data.startswith("list_keys_"))
async def list_keys(callback: CallbackQuery):
    provider_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        api_key_repo = APIKeyRepository(session)
        ai_provider_repo = AIProviderRepository(session)

        provider = await ai_provider_repo.get_by_id(provider_id)
        api_keys = await api_key_repo.get_by_provider(provider_id)

    if not api_keys:
        await callback.answer("❌ Нет ключей", show_alert=True)
        return

    text = f"📋 <b>Ключи {provider.display_name}</b>\n\nВыберите ключ для управления:\n\n"

    keyboard = []
    for key in api_keys:
        status = "✅" if key.is_active else "❌"
        name = key.name or f"Ключ {key.id}"
        btn_text = f"{status} {name}"

        keyboard.append([InlineKeyboardButton(
            text=btn_text,
            callback_data=f"manage_key_{key.id}"
        )])

    keyboard.append([InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=f"provider_{provider_id}"
    )])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("manage_key_"))
async def manage_key(callback: CallbackQuery):
    key_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        api_key_repo = APIKeyRepository(session)
        key = await api_key_repo.get_by_id(key_id)

        if not key:
            await callback.answer("❌ Ключ не найден", show_alert=True)
            return

    text = f"🔑 <b>Управление ключом</b>\n\n"
    text += f"<b>Название:</b> {key.name or f'Ключ {key.id}'}\n"
    text += f"<b>Статус:</b> {'✅ Активен' if key.is_active else '❌ Неактивен'}\n"
    text += f"<b>Ключ:</b> <code>{key.api_key[:10]}...{key.api_key[-4:]}</code>\n\n"

    if key.requests_limit:
        text += f"<b>Лимит:</b> {key.requests_made}/{key.requests_limit}\n"
    else:
        text += f"<b>Использовано:</b> {key.requests_made} (безлимит)\n"

    if key.last_error:
        text += f"\n⚠️ <b>Последняя ошибка:</b>\n{key.last_error[:200]}\n"

    keyboard = [
        [InlineKeyboardButton(
            text="❌ Деактивировать" if key.is_active else "✅ Активировать",
            callback_data=f"toggle_key_{key_id}"
        )],
        [InlineKeyboardButton(
            text="🗑 Удалить ключ",
            callback_data=f"delete_key_{key_id}"
        )],
        [InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"list_keys_{key.provider_id}"
        )]
    ]

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("toggle_key_"))
async def toggle_key(callback: CallbackQuery):
    key_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        api_key_repo = APIKeyRepository(session)
        key = await api_key_repo.get_by_id(key_id)

        if key.is_active:
            await api_key_repo.deactivate(key_id)
            await callback.answer("❌ Ключ деактивирован", show_alert=True)
        else:
            await api_key_repo.activate(key_id)
            await callback.answer("✅ Ключ активирован", show_alert=True)

    await manage_key(callback)

@router.callback_query(F.data.startswith("delete_key_"))
async def delete_key(callback: CallbackQuery):
    key_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        api_key_repo = APIKeyRepository(session)
        key = await api_key_repo.get_by_id(key_id)
        provider_id = key.provider_id

        await api_key_repo.delete(key_id)

    await callback.answer("🗑 Ключ удален", show_alert=True)

    await callback.message.edit_text("Ключ удален. Возвращаюсь к списку...")
    callback.data = f"list_keys_{provider_id}"
    await list_keys(callback)

@router.callback_query(F.data.startswith("manage_models_"))
async def show_models_menu(callback: CallbackQuery):
    provider_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        ai_provider_repo = AIProviderRepository(session)
        model_repo = AIModelRepository(session)

        provider = await ai_provider_repo.get_by_id(provider_id)
        if not provider:
            await callback.answer("❌ Провайдер не найден", show_alert=True)
            return

        models = await model_repo.get_by_provider(provider_id)

    text = f"🎯 <b>Модели {provider.display_name}</b>\n\n"

    if models:
        for i, model in enumerate(models, 1):
            status = "✅" if model.is_active else "❌"
            default = " 🌟 (основная)" if model.is_default else ""
            name = model.display_name or model.model_name
            text += f"{i}. {status} {name}{default}\n"
            text += f"   Код: <code>{model.model_name}</code>\n"
            if model.last_error:
                text += f"   ⚠️ Ошибка: {model.last_error[:50]}...\n"
            text += "\n"
    else:
        text += "Нет моделей. Добавьте хотя бы одну модель.\n"

    keyboard = [
        [InlineKeyboardButton(
            text="➕ Добавить модель",
            callback_data=f"add_model_{provider_id}"
        )],
        [InlineKeyboardButton(
            text="📋 Управление моделями",
            callback_data=f"list_models_{provider_id}"
        )],
        [InlineKeyboardButton(
            text="⬅️ Назад",
            callback_data=f"provider_{provider_id}"
        )]
    ]

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("add_model_"))
async def request_add_model(callback: CallbackQuery, state: FSMContext):
    provider_id = int(callback.data.split("_")[2])

    await state.update_data(provider_id=provider_id)
    await state.set_state(AdminStates.entering_model_name)

    async with get_session() as session:
        ai_provider_repo = AIProviderRepository(session)
        provider = await ai_provider_repo.get_by_id(provider_id)

    examples = {
        'groq': '• llama-3.1-8b-instant\n• mixtral-8x7b-32768',
        'openai': '• gpt-4\n• gpt-3.5-turbo',
        'openrouter': '• deepseek/deepseek-r1-0528:free\n• openai/gpt-3.5-turbo'
    }

    example_text = examples.get(provider.name, '• model-name')

    await callback.message.answer(
        f"➕ <b>Добавление модели для {provider.display_name}</b>\n\n"
        f"Отправьте код модели:\n\n"
        f"<b>Примеры:</b>\n{example_text}",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(AdminStates.entering_model_name)
async def receive_model_name(message: Message, state: FSMContext):
    model_name = message.text.strip()

    await state.update_data(model_name=model_name)
    await state.set_state(AdminStates.entering_model_display_name)

    await message.answer(
        f"✅ Код модели: <code>{model_name}</code>\n\n"
        f"Теперь отправьте отображаемое имя для модели (для админки):\n"
        f"Например: <i>GPT-4 Turbo</i> или <i>Llama 3.1 8B</i>\n\n"
        f"Или отправьте <code>-</code> чтобы использовать код модели.",
        parse_mode="HTML"
    )

@router.message(AdminStates.entering_model_display_name)
async def save_new_model(message: Message, state: FSMContext):
    data = await state.get_data()
    provider_id = data.get("provider_id")
    model_name = data.get("model_name")
    display_name = message.text.strip()

    if display_name == "-":
        display_name = None

    async with get_session() as session:
        model_repo = AIModelRepository(session)
        admin_repo = AdminRepository(session)

        existing_models = await model_repo.get_by_provider(provider_id)
        is_default = len(existing_models) == 0

        await model_repo.create(
            provider_id=provider_id,
            model_name=model_name,
            display_name=display_name,
            is_default=is_default
        )

        await admin_repo.log_action(
            message.from_user.id,
            "add_model",
            details=f"Provider ID: {provider_id}, Model: {model_name}"
        )

    default_msg = " и установлена как основная" if is_default else ""
    await message.answer(
        f"✅ Модель <code>{model_name}</code> добавлена{default_msg}!",
        parse_mode="HTML"
    )
    await state.clear()

@router.callback_query(F.data.startswith("list_models_"))
async def list_models_for_management(callback: CallbackQuery):
    provider_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        model_repo = AIModelRepository(session)
        ai_provider_repo = AIProviderRepository(session)

        provider = await ai_provider_repo.get_by_id(provider_id)
        models = await model_repo.get_by_provider(provider_id)

    if not models:
        await callback.answer("❌ Нет моделей для управления", show_alert=True)
        return

    text = f"📋 <b>Управление моделями {provider.display_name}</b>\n\n"
    text += "Выберите модель:\n\n"

    keyboard = []
    for model in models:
        status = "✅" if model.is_active else "❌"
        default = "🌟" if model.is_default else ""
        name = model.display_name or model.model_name
        keyboard.append([InlineKeyboardButton(
            text=f"{status} {name} {default}",
            callback_data=f"model_detail_{model.id}"
        )])

    keyboard.append([InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=f"manage_models_{provider_id}"
    )])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("model_detail_"))
async def show_model_detail(callback: CallbackQuery):
    model_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        model_repo = AIModelRepository(session)
        ai_provider_repo = AIProviderRepository(session)

        model = await model_repo.get_by_id(model_id)
        if not model:
            await callback.answer("❌ Модель не найдена", show_alert=True)
            return

        provider = await ai_provider_repo.get_by_id(model.provider_id)

    text = f"🎯 <b>Модель: {model.display_name or model.model_name}</b>\n\n"
    text += f"<b>Провайдер:</b> {provider.display_name}\n"
    text += f"<b>Код модели:</b> <code>{model.model_name}</code>\n"
    text += f"<b>Статус:</b> {'✅ Активна' if model.is_active else '❌ Неактивна'}\n"
    text += f"<b>По умолчанию:</b> {'Да 🌟' if model.is_default else 'Нет'}\n"
    text += f"<b>Ошибок:</b> {model.error_count}\n"

    if model.last_error:
        text += f"\n<b>Последняя ошибка:</b>\n<code>{model.last_error[:200]}</code>\n"

    if model.last_used_at:
        text += f"\n<b>Последнее использование:</b> {model.last_used_at.strftime('%Y-%m-%d %H:%M')}\n"

    keyboard = []

    if model.is_active:
        keyboard.append([InlineKeyboardButton(
            text="❌ Деактивировать",
            callback_data=f"toggle_model_{model.id}"
        )])
    else:
        keyboard.append([InlineKeyboardButton(
            text="✅ Активировать",
            callback_data=f"toggle_model_{model.id}"
        )])

    if not model.is_default:
        keyboard.append([InlineKeyboardButton(
            text="🌟 Сделать основной",
            callback_data=f"set_default_model_{model.id}"
        )])

    keyboard.append([InlineKeyboardButton(
        text="🗑 Удалить модель",
        callback_data=f"delete_model_{model.id}"
    )])

    keyboard.append([InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=f"list_models_{provider.id}"
    )])

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data.startswith("toggle_model_"))
async def toggle_model_status(callback: CallbackQuery):
    model_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        model_repo = AIModelRepository(session)
        model = await model_repo.get_by_id(model_id)

        if model.is_active:
            await model_repo.deactivate(model_id)
            status_text = "деактивирована"
        else:
            await model_repo.activate(model_id)
            status_text = "активирована"

    await callback.answer(f"✅ Модель {status_text}", show_alert=True)

    await show_model_detail(callback)

@router.callback_query(F.data.startswith("set_default_model_"))
async def set_default_model(callback: CallbackQuery):
    model_id = int(callback.data.split("_")[3])

    async with get_session() as session:
        model_repo = AIModelRepository(session)
        model = await model_repo.get_by_id(model_id)

        if model:
            await model_repo.set_default(model_id)

    await callback.answer("✅ Модель установлена по умолчанию", show_alert=True)

    await show_model_detail(callback)

@router.callback_query(F.data.startswith("delete_model_"))
async def delete_model(callback: CallbackQuery):
    model_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        model_repo = AIModelRepository(session)
        model = await model_repo.get_by_id(model_id)

        if not model:
            await callback.answer("❌ Модель не найдена", show_alert=True)
            return

        provider_id = model.provider_id

        models = await model_repo.get_by_provider(provider_id)
        if len(models) <= 1:
            await callback.answer(
                "❌ Нельзя удалить последнюю модель провайдера",
                show_alert=True
            )
            return

        if model.is_default and len(models) > 1:
            for other_model in models:
                if other_model.id != model_id:
                    await model_repo.set_default(other_model.id)
                    break

        await model_repo.delete(model_id)

    await callback.answer("✅ Модель удалена", show_alert=True)

    callback.data = f"list_models_{provider_id}"
    await list_models_for_management(callback)

@router.callback_query(F.data.startswith("set_default_"))
async def set_default_provider(callback: CallbackQuery):
    provider_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        ai_provider_repo = AIProviderRepository(session)
        await ai_provider_repo.update(provider_id=provider_id, is_default=True)

    await callback.answer("✅ Провайдер установлен по умолчанию", show_alert=True)
    await show_provider_detail(callback)

@router.callback_query(F.data.startswith("delete_provider_"))
async def delete_provider(callback: CallbackQuery):
    provider_id = int(callback.data.split("_")[2])

    async with get_session() as session:
        ai_provider_repo = AIProviderRepository(session)
        provider = await ai_provider_repo.get_by_id(provider_id)

        if provider.is_default:
            await callback.answer(
                "❌ Нельзя удалить основного провайдера. Сначала сделайте другого основным.",
                show_alert=True
            )
            return

        await ai_provider_repo.delete(provider_id)

    await callback.answer("🗑 Провайдер удален", show_alert=True)
    await show_providers_list(callback)

