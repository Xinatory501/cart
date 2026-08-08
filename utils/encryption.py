from __future__ import annotations
import base64
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

def _get_fernet():
    try:
        from cryptography.fernet import Fernet
        key = os.environ.get('SECRET_ENCRYPTION_KEY', '')
        if not key:
            # Generate and warn
            key = Fernet.generate_key().decode()
            logger.warning('SECRET_ENCRYPTION_KEY not set, generated ephemeral key. Set this in .env!')
        if isinstance(key, str):
            key = key.encode()
        return Fernet(key)
    except ImportError:
        return None

def encrypt_value(plaintext: str) -> str:
    """SEC-04: Encrypt sensitive value. Returns base64 prefixed with 'enc:'"""
    if not plaintext or plaintext.startswith('enc:'):
        return plaintext
    f = _get_fernet()
    if not f:
        return plaintext  # fallback: no encryption library
    try:
        token = f.encrypt(plaintext.encode()).decode()
        return f'enc:{token}'
    except Exception as e:
        logger.error('Encryption failed: %s', e)
        return plaintext

def decrypt_value(ciphertext: str) -> str:
    """SEC-04: Decrypt value encrypted with encrypt_value."""
    if not ciphertext or not ciphertext.startswith('enc:'):
        return ciphertext  # plaintext, return as-is
    f = _get_fernet()
    if not f:
        return ciphertext
    try:
        token = ciphertext[4:]  # strip 'enc:'
        return f.decrypt(token.encode()).decode()
    except Exception as e:
        logger.error('Decryption failed: %s', e)
        return ciphertext

def mask_key(key: str) -> str:
    """Return masked fingerprint: first 4 + ... + last 4 chars"""
    if not key or len(key) < 10:
        return '***'
    plain = decrypt_value(key) if key.startswith('enc:') else key
    if len(plain) <= 8:
        return '***'
    return f'{plain[:4]}...{plain[-4:]}'
