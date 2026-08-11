from __future__ import annotations
import pytest
import os
import json
from unittest.mock import MagicMock

from utils.encryption import encrypt_value, decrypt_value
from database.repository import APIKeyRepository
from services.web_server import SessionTokenManager
from adapters.sqb_adapter import SqbBankAdapter
from adapters.nivea_adapter import NiveaLoyaltyAdapter
from adapters.bitrix24_adapter import BitrixTaskAdapter

def test_sqb_card_masking():
    adapter = SqbBankAdapter("http://sqb.uz", "cert.pem")
    pan = "8600123456789012"
    masked = adapter._mask_card_number(pan)
    assert masked == "860012******9012"
    
    pan_short = "1234"
    assert adapter._mask_card_number(pan_short) == "****"

def test_session_token_manager():
    secret = "my-secret-key-for-testing"
    user_id = 99128
    session_id = 452
    
    token = SessionTokenManager.generate_token(user_id, session_id, secret)
    assert token is not None
    assert len(token.split(".")) == 2
    
    payload = SessionTokenManager.verify_token(token, secret)
    assert payload is not None
    assert payload["user_id"] == user_id
    assert payload["session_id"] == session_id
    
    # Mismatch secret
    assert SessionTokenManager.verify_token(token, "wrong-secret") is None

def test_api_key_normalization():
    raw_key = '  "Bearer sk-live-key-12345"  '
    normalized = APIKeyRepository.normalize_api_key(raw_key)
    assert normalized == "sk-live-key-12345"

def test_encryption_decryption():
    from cryptography.fernet import Fernet
    os.environ["SECRET_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
    plaintext = "super-secret-api-key"
    
    encrypted = encrypt_value(plaintext)
    assert encrypted.startswith("enc:")
    
    decrypted = decrypt_value(encrypted)
    assert decrypted == plaintext
