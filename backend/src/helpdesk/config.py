from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    app_timezone: str = "America/Mexico_City"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "postgresql+asyncpg://helpdesk:helpdesk@localhost:5432/helpdesk"
    db_pool_size: int = 10
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: SecretStr = Field(min_length=32)
    jwt_issuer: str = "helpdesk-ti"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    cookie_secure: bool = True
    login_max_attempts: int = 5
    login_lock_minutes: int = 15
    tab_lease_ttl_seconds: int = 90

    sla_critical_hours: int = 4
    sla_high_hours: int = 8
    sla_medium_hours: int = 24
    sla_low_hours: int = 72

    seed_admin_email: str = "admin@helpdesk.test"
    seed_admin_password: SecretStr | None = None
    seed_user_email: str = "usuario@helpdesk.test"
    seed_user_password: SecretStr | None = None
    seed_observer_email: str = "observador@helpdesk.test"
    seed_observer_password: SecretStr | None = None
    seed_demo_data: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()  # los valores obligatorios vienen del entorno
