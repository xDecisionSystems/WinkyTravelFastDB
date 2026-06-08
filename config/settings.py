from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    api_host: str
    api_port: int
    google_maps_api_key: str
    google_places_base_url: str
    google_timeout_seconds: float
    environment: str
    service_name: str
    rate_limit_per_second: int
    rate_limit_per_hour: int
    rate_limit_per_day: int
    rate_limit_retention_hours: int
    dev_master_api_key: str
    dev_log_root_dir: str
    dev_log_max_bytes: int
    dev_log_max_lines: int
    google_client_id: str
    jwt_secret_key: str
    jwt_expiry_hours: int
    dev_login_enabled: bool
    dev_login_master_key: str
    cors_allowed_origins: list[str]


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _optional(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def _optional_positive_int(name: str, default: str) -> int:
    value = int(_optional(name, default))
    if value <= 0:
        raise RuntimeError(f"Environment variable {name} must be > 0")
    return value


def _optional_bool(name: str, default: str) -> bool:
    return _optional(name, default).lower() in {"1", "true", "yes", "on"}


def _optional_csv(name: str, default: str) -> list[str]:
    raw = _optional(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _database_url() -> str:
    # Backward compatibility for older deployments.
    explicit_url = _optional("DATABASE_URL", "")
    if explicit_url:
        return explicit_url

    db_host = _required("DB_HOST")
    db_port = _optional_positive_int("DB_PORT", "5432")
    db_name = _required("DB_NAME")
    db_user = _required("DB_USER")
    db_password = _optional("DB_PASSWORD", "")
    db_sslmode = _optional("DB_SSLMODE", "disable")

    encoded_user = quote(db_user, safe="")
    encoded_db_name = quote(db_name, safe="")
    if db_password:
        credentials = f"{encoded_user}:{quote(db_password, safe='')}"
    else:
        credentials = encoded_user

    return (
        f"postgresql://{credentials}@{db_host}:{db_port}/{encoded_db_name}"
        f"?sslmode={quote(db_sslmode, safe='')}"
    )


settings = Settings(
    database_url=_database_url(),
    api_host=_optional("API_HOST", "0.0.0.0"),
    api_port=int(_optional("API_PORT", "8000")),
    google_maps_api_key=_optional("GOOGLE_MAPS_API_KEY", ""),
    google_places_base_url=_optional("GOOGLE_PLACES_BASE_URL", "https://places.googleapis.com/v1"),
    google_timeout_seconds=float(_optional("GOOGLE_TIMEOUT_SECONDS", "8")),
    environment=_optional("ENVIRONMENT", "development"),
    service_name=_optional("SERVICE_NAME", "winky-travel-fastdb"),
    rate_limit_per_second=_optional_positive_int("RATE_LIMIT_PER_SECOND", "5"),
    rate_limit_per_hour=_optional_positive_int("RATE_LIMIT_PER_HOUR", "1000"),
    rate_limit_per_day=_optional_positive_int("RATE_LIMIT_PER_DAY", "10000"),
    rate_limit_retention_hours=_optional_positive_int("RATE_LIMIT_RETENTION_HOURS", "48"),
    dev_master_api_key=_optional("DEV_MASTER_API_KEY", ""),
    dev_log_root_dir=_optional("DEV_LOG_ROOT_DIR", "/var/log"),
    dev_log_max_bytes=_optional_positive_int("DEV_LOG_MAX_BYTES", "131072"),
    dev_log_max_lines=_optional_positive_int("DEV_LOG_MAX_LINES", "400"),
    google_client_id=_required("GOOGLE_CLIENT_ID"),
    jwt_secret_key=_required("JWT_SECRET_KEY"),
    jwt_expiry_hours=_optional_positive_int("JWT_EXPIRY_HOURS", "168"),
    dev_login_enabled=_optional_bool("DEV_LOGIN_ENABLED", "false"),
    dev_login_master_key=_optional("DEV_LOGIN_MASTER_KEY", ""),
    cors_allowed_origins=_optional_csv("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"),
)
