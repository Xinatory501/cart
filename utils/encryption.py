from __future__ import annotations
import base64
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Config for HashiCorp Vault (ADM-04)
VAULT_ADDR = os.environ.get('VAULT_ADDR', '')
VAULT_TOKEN = os.environ.get('VAULT_TOKEN', '')
VAULT_MOUNT_POINT = os.environ.get('VAULT_MOUNT_POINT', 'transit')
VAULT_KEY_NAME = os.environ.get('VAULT_KEY_NAME', 'cartame-key')

_vault_client = None

def _get_vault_client():
    global _vault_client
    if _vault_client is not None:
        return _vault_client
    if not VAULT_ADDR or not VAULT_TOKEN:
        return None
    try:
        import hvac
        client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
        if client.is_authenticated():
            _vault_client = client
            logger.info('Successfully authenticated with HashiCorp Vault at %s', VAULT_ADDR)
            return _vault_client
    except Exception as e:
        logger.error('Failed to initialize Vault client: %s', e)
    return None

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
    """SEC-04 / ADM-04: Encrypt sensitive value. Returns ciphertext with 'vault:' or 'enc:' prefix."""
    if not plaintext or plaintext.startswith('enc:') or plaintext.startswith('vault:'):
        return plaintext
    
    client = _get_vault_client()
    if client:
        try:
            b64_plaintext = base64.b64encode(plaintext.encode()).decode()
            response = client.secrets.transit.encrypt_data(
                name=VAULT_KEY_NAME,
                plaintext=b64_plaintext,
                mount_point=VAULT_MOUNT_POINT
            )
            ciphertext = response['data']['ciphertext']
            return f"vault:{ciphertext}"
        except Exception as e:
            logger.error('Vault encryption failed: %s. Falling back to Fernet.', e)
            
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
    """SEC-04 / ADM-04: Decrypt value encrypted with Vault or local Fernet."""
    if not ciphertext:
        return ciphertext
        
    if ciphertext.startswith('vault:'):
        client = _get_vault_client()
        if client:
            try:
                vault_ciphertext = ciphertext[6:]  # strip 'vault:'
                response = client.secrets.transit.decrypt_data(
                    name=VAULT_KEY_NAME,
                    ciphertext=vault_ciphertext,
                    mount_point=VAULT_MOUNT_POINT
                )
                b64_plaintext = response['data']['plaintext']
                return base64.b64decode(b64_plaintext.encode()).decode()
            except Exception as e:
                logger.error('Vault decryption failed: %s', e)
                return ciphertext
        else:
            logger.warning('Vault ciphertext found but Vault client is not configured')
            return ciphertext

    if not ciphertext.startswith('enc:'):
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
    plain = decrypt_value(key)
    if len(plain) <= 8:
        return '***'
    return f'{plain[:4]}...{plain[-4:]}'
