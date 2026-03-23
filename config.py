from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):

    BOT1_TOKEN: str = ""
    BOT2_TOKEN: str = ""
    BOT3_TOKEN: str = ""
    BOT1_TOKE: str = ""
    BOT2_TOKE: str = ""
    BOT3_TOKE: str = ""
    SUPPORT_GROUP_ID: Optional[int] = None

    ADMIN_IDS: str = ""

    DATABASE_URL: str = "sqlite+aiosqlite:///data/cartame_bot.db"
    DEFAULT_LANGUAGE: str = "en"

    @property
    def admin_ids(self) -> List[int]:
        if not self.ADMIN_IDS:
            return []
        return [int(id.strip()) for id in self.ADMIN_IDS.split(',') if id.strip()]

    @property
    def bot1_token(self) -> str:
        return (self.BOT1_TOKEN or self.BOT1_TOKE or "").strip()

    @property
    def bot2_token(self) -> str:
        return (self.BOT2_TOKEN or self.BOT2_TOKE or "").strip()

    @property
    def bot3_token(self) -> str:
        return (self.BOT3_TOKEN or self.BOT3_TOKE or "").strip()

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
