from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    mongo_uri: str
    mongo_db: str
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


settings = Settings(
    mongo_uri=_required("MONGO_URI"),
    mongo_db=_required("MONGO_DB"),
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
)
