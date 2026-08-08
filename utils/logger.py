from __future__ import annotations
import logging
import json
import os
from datetime import datetime
from typing import Optional

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if record.exc_info:
            log_record['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)

def setup_logger(level: str = None) -> None:
    log_level = getattr(logging, (level or os.getenv('LOG_LEVEL', 'INFO')).upper(), logging.INFO)
    log_format = os.getenv('LOG_FORMAT', 'text')  # 'text' or 'json'
    
    handler = logging.StreamHandler()
    if log_format == 'json':
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))
    
    root = logging.getLogger()
    root.setLevel(log_level)
    root.handlers.clear()
    root.addHandler(handler)
    
    # Suppress noisy loggers
    for noisy in ('aiogram', 'aiohttp', 'asyncio', 'sqlalchemy.engine'):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    
    logging.getLogger(__name__).info('Logger configured successfully')

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
