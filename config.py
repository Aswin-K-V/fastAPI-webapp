import logging
import re
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    

    database_url:str
    
    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    max_upload_size_bytes: int = 5 * 1024 * 1024
    posts_per_page: int = 5

    reset_token_expire_minutes: int = 60
    mail_server: str = "localhost"
    mail_port: int = 587
    mail_username: str = ""
    mail_password: SecretStr = SecretStr("")
    mail_from: str = "noreply@example.com"
    mail_use_tls: bool = True
    frontend_url: str = "http://localhost:8000"

    s3_bucket_name: str | None = None
    s3_region: str | None = None
    s3_access_key_id:SecretStr | None = None
    s3_secret_access_key:SecretStr | None =None
    s3_endpoint_url:str | None =None

    # Logging
    log_level: str = "INFO"
    log_format: Literal["plain", "json"] = "json"
    log_dir: str = "logs"
    log_file_name: str = "app.log"
    log_to_file: bool = True
    log_to_console: bool = True
    log_max_bytes: int = 10 * 1024 * 1024  # 10 MB per file (size-based rotation)
    log_backup_count: int = 5  # app.log.1 .. app.log.5
    log_requests: bool = True
    log_uvicorn_access: bool = True

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        level = str(value).strip().upper()
        valid = logging.getLevelNamesMapping()
        if level not in valid:
            allowed = ", ".join(sorted(valid))
            raise ValueError(
                f"LOG_LEVEL must be one of: {allowed}; got {value!r}"
            )
        return level

    @staticmethod
    def _is_region_code(value: str) -> bool:
        return re.fullmatch(r"[a-z]{2}(?:-[a-z0-9]+)+-\d+", value) is not None

    @field_validator("s3_region", mode="before")
    @classmethod
    def normalize_s3_region(cls, value: str | None) -> str | None:
        if value is None:
            return None

        region = str(value).strip()
        if not region:
            return None

        if cls._is_region_code(region):
            return region

        candidate = region.rsplit(maxsplit=1)[-1]
        if cls._is_region_code(candidate):
            return candidate

        return region

    def missing_s3_settings(self) -> list[str]:
        missing: list[str] = []
        if not self.s3_bucket_name:
            missing.append("S3_BUCKET_NAME")
        if not self.s3_region:
            missing.append("S3_REGION")
        return missing

    def require_s3_settings(self) -> None:
        missing = self.missing_s3_settings()
        if missing:
            values = "\n".join(f"{name}=..." for name in missing)
            raise RuntimeError(
                "S3 configuration is incomplete. Add these values to .env:\n"
                f"{values}"
            )

        if self.s3_region and not self._is_region_code(self.s3_region):
            raise RuntimeError(
                "S3_REGION must be an AWS region code like ap-southeast-2, "
                f"not {self.s3_region!r}."
            )





settings = Settings()  # loaded from env
