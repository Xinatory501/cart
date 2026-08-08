from __future__ import annotations
import time
from collections import defaultdict
from typing import Dict, Tuple

class InMemoryRateLimiter:
    """
    WEB-09: Per-IP / per-session rate limiter.
    Simple sliding window implementation.
    """
    def __init__(self, requests_per_minute: int = 60):
        self.rpm = requests_per_minute
        self._windows: Dict[str, list] = defaultdict(list)
    
    def is_allowed(self, key: str) -> Tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)"""
        now = time.time()
        window = self._windows[key]
        # Remove entries older than 60 seconds
        cutoff = now - 60
        while window and window[0] < cutoff:
            window.pop(0)
        
        if len(window) >= self.rpm:
            retry_after = int(60 - (now - window[0])) + 1
            return False, retry_after
        
        window.append(now)
        return True, 0
    
    def cleanup(self) -> None:
        """Remove empty windows."""
        now = time.time()
        cutoff = now - 60
        for key in list(self._windows.keys()):
            self._windows[key] = [t for t in self._windows[key] if t > cutoff]
            if not self._windows[key]:
                del self._windows[key]


ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'application/pdf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def validate_upload(file_bytes: bytes, filename: str, content_type: str) -> Tuple[bool, str]:
    """
    WEB-08: Validate uploaded file for type, size, and magic bytes.
    """
    if len(file_bytes) > MAX_FILE_SIZE:
        return False, f'Файл слишком большой (макс {MAX_FILE_SIZE // 1024 // 1024}MB)'
    
    if content_type not in ALLOWED_MIME_TYPES:
        return False, f'Тип файла не разрешён: {content_type}'
    
    # Magic byte check
    MAGIC = {
        b'\xff\xd8\xff': 'image/jpeg',
        b'\x89PNG': 'image/png',
        b'GIF8': 'image/gif',
        b'RIFF': 'image/webp',
        b'%PDF': 'application/pdf',
    }
    detected = None
    for magic, mime in MAGIC.items():
        if file_bytes[:len(magic)] == magic:
            detected = mime
            break
    
    if detected and detected != content_type:
        return False, f'Тип файла не совпадает с содержимым'
    
    return True, 'ok'


def generate_safe_filename(original: str) -> str:
    """WEB-08: Generate random safe filename to prevent path traversal."""
    import uuid
    import os
    ext = os.path.splitext(original)[-1].lower()
    if ext not in {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.pdf'}:
        ext = ''
    return f'{uuid.uuid4().hex}{ext}'
