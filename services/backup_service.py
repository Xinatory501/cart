
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.engine.url import make_url

from config import settings


def _resolve_db_path(db_url: str) -> Optional[Path]:
    try:
        url = make_url(db_url)
    except Exception:
        return None

    if not url.drivername.startswith("sqlite"):
        return None

    db_path = url.database
    if not db_path or db_path == ":memory:":
        return None

    path = Path(db_path)
    if not path.is_absolute():
        base_dir = Path(__file__).resolve().parents[1]
        path = base_dir / db_path
    return path

class BackupService:

    def __init__(self, db_path: Optional[str] = None):
        if db_path:
            self.db_path = str(Path(db_path))
            return

        resolved = _resolve_db_path(settings.DATABASE_URL)
        self.db_path = str(resolved) if resolved else "cartame_bot.db"

    async def create_backup(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"backup_{timestamp}.db"

        shutil.copy2(self.db_path, backup_path)
        return backup_path

    async def restore_backup(self, backup_path: str):
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, self.db_path)
