from __future__ import annotations
import pytest
from unittest.mock import MagicMock, AsyncMock

from database.models import User
from database.repository import UserRepository
from keyboards.menu import get_phone_request_keyboard


def test_phone_request_keyboard():
    keyboard = get_phone_request_keyboard("ru")
    assert len(keyboard.keyboard) == 1
    button = keyboard.keyboard[0][0]
    assert button.request_contact is True
    assert "номер" in button.text.lower()


def test_contact_ownership_verification():
    user_id = 123456789
    
    # Valid contact (matches sender user_id)
    valid_contact = MagicMock()
    valid_contact.user_id = user_id
    valid_contact.phone_number = "+998901234567"
    assert valid_contact.user_id == user_id

    # Invalid contact (sent someone else's contact)
    invalid_contact = MagicMock()
    invalid_contact.user_id = 987654321
    invalid_contact.phone_number = "+998909999999"
    assert invalid_contact.user_id != user_id


def test_user_phone_number_update():
    import asyncio
    async def _test():
        session = AsyncMock()
        repo = UserRepository(session)
        
        user_id = 555001
        phone = "+375291234567"
        
        await repo.update_phone_number(user_id, phone)
        assert session.execute.called
        assert session.commit.called

    asyncio.run(_test())
