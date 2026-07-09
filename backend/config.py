from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path
from typing import Optional
import os
import sys

if sys.platform == "win32":
    import winreg


BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent


def get_windows_registry_env(name: str) -> Optional[str]:
    """Read User/Machine environment variables on Windows if not inherited."""
    if sys.platform != "win32":
        return None

    registry_locations = [
        (winreg.HKEY_CURRENT_USER, "Environment"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
    ]
    for root, path in registry_locations:
        try:
            with winreg.OpenKey(root, path) as key:
                value, _ = winreg.QueryValueEx(key, name)
                if value:
                    return str(value)
        except OSError:
            continue
    return None


def get_env_value(name: str) -> Optional[str]:
    return os.getenv(name) or get_windows_registry_env(name)


class Settings(BaseSettings):
    # Database
    SQLITE_DB_PATH: str = str(PROJECT_DIR / "data" / "market_data.sqlite3")
    DB_PATH: Optional[str] = None

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        case_sensitive=True,
        extra="ignore",
    )

    def model_post_init(self, __context):
        """Apply supported env aliases."""
        db_path = self.DB_PATH or get_env_value("DB_PATH")
        if db_path:
            self.SQLITE_DB_PATH = db_path

    def sqlite_db_path(self) -> Path:
        path = Path(self.SQLITE_DB_PATH).expanduser()
        if not path.is_absolute():
            path = PROJECT_DIR / path
        return path

    def cors_origins(self) -> list[str]:
        origins = [
            origin.strip()
            for origin in (self.CORS_ORIGINS or "").split(",")
            if origin.strip()
        ]
        return origins or ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()
