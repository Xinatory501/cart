
import logging
import sys
from typing import Optional

def setup_logger(level: Optional[int] = None) -> None:
    if level is None:
        level = logging.INFO

    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )

    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)

    logger = logging.getLogger(__name__)
    logger.info("Logger configured successfully")

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
