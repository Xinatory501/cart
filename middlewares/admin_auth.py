from __future__ import annotations
import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from database.database import get_session
from database.repository import UserRepository, AdminRepository
from config import settings

logger = logging.getLogger(__name__)

class AdminAuthMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]],
        event: Any,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        is_admin_action = False
        action_name = "unknown"

        # Извлекаем FSMContext для проверки состояния
        state: FSMContext = data.get("state")
        current_state = None
        if state:
            current_state = await state.get_state()

        if isinstance(event, CallbackQuery):
            user_id = event.from_user.id
            callback_data = event.data or ""
            # Если callback относится к админке или настройкам
            is_admin_action = (
                callback_data.startswith("admin_") or
                callback_data.startswith("provider_") or
                callback_data.startswith("key_") or
                callback_data.startswith("antiflood_") or
                callback_data.startswith("backup_") or
                callback_data.startswith("policy_") or
                callback_data.startswith("reports_")
            )
            action_name = f"callback:{callback_data}"

        elif isinstance(event, Message):
            user_id = event.from_user.id
            text = event.text or ""
            # Если команда администратора или пользователь находится в админском FSM состоянии
            is_admin_action = (
                text.startswith("/admin") or
                text.startswith("/download") or
                text.startswith("/upload") or
                text.startswith("/export") or
                text.startswith("/antiflood")
            )
            if not is_admin_action and current_state:
                # Если имя FSM состояния относится к админским модулям
                state_lower = current_state.lower()
                is_admin_action = any(
                    k in state_lower for k in ["admin", "provider", "antiflood", "backup", "kb_", "training", "policy", "branding"]
                )
            action_name = f"message:{text[:20]}" if not current_state else f"state:{current_state}"

        # Если это не админское действие, пропускаем дальше
        if not is_admin_action:
            return await handler(event, data)

        # Проверяем роль пользователя в БД (или settings.admin_ids)
        is_super = user_id in settings.admin_ids
        user_role = "user"
        
        async with get_session() as session:
            user_repo = UserRepository(session)
            db_user = await user_repo.get_by_id(user_id)
            if db_user:
                user_role = db_user.role

        # Проверяем роли (RBAC) (CT-P0-06)
        # Суперадмин может всё
        if is_super or user_role in ("superadmin", "project_admin") and user_role == "superadmin":
            await self._log_audit(user_id, "superadmin", action_name, "ALLOWED")
            return await handler(event, data)

        # Роль project_admin ограничена: не может управлять ключами, провайдерами или бэкапами
        if user_role == "project_admin" or (is_super and user_role == "project_admin"):
            forbidden_keywords = ["backup", "key", "provider", "download", "upload", "antiflood"]
            if any(k in action_name.lower() for k in forbidden_keywords):
                logger.warning(f"RBAC blocked project_admin: user={user_id} tried={action_name}")
                await self._log_audit(user_id, "project_admin", action_name, "DENIED")
                if isinstance(event, CallbackQuery):
                    await event.answer("⛔ Системные настройки (бэкапы, ключи, антифлуд) доступны только суперадминистратору", show_alert=True)
                elif isinstance(event, Message):
                    await event.answer("⛔ Системные настройки (бэкапы, ключи, антифлуд) доступны только суперадминистратору")
                return
            await self._log_audit(user_id, "project_admin", action_name, "ALLOWED")
            return await handler(event, data)

        # Все остальные роли блокируются
        logger.warning(f"Unauthorized admin access attempt: user={user_id} role={user_role} action={action_name}")
        await self._log_audit(user_id, user_role, action_name, "DENIED")
        
        if isinstance(event, CallbackQuery):
            await event.answer("⛔ Доступ запрещён", show_alert=True)
        elif isinstance(event, Message):
            await event.answer("⛔ Доступ запрещён")
        return

    async def _log_audit(self, user_id: int, role: str, action: str, result: str):
        """Запись административного действия в аудит-лог в БД."""
        try:
            async with get_session() as session:
                from database.repository import AdminRepository
                admin_repo = AdminRepository(session)
                await admin_repo.log_action(
                    admin_id=user_id,
                    action_type=f"{role}_{result}",
                    details=f"Action: {action}"
                )
        except Exception as e:
            logger.error("Failed to write admin audit log: %s", e)
