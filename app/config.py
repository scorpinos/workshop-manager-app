from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    SECRET_KEY = "change-this-secret-in-production"
    DATABASE = BASE_DIR / "app" / "data" / "workshop.sqlite3"
    BACKUP_DIR = BASE_DIR / "backups"
    UPLOAD_DIR = BASE_DIR / "app" / "static" / "uploads"
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
