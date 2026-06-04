"""
This is where you can define your application settings using Pydantic's BaseSettings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "Dloomberg Service"
    VERSION: str = "0.1.0"
    DEBUG: bool = False
    PROXY_URL: str | None = None
    HOST: str = "localhost"
    PORT: int = 8000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"             # dont raise error for extra fields in .env
    )


# 使用 lru_cache 确保配置对象只被加载和实例化一次（单例模式）
# Gemini generated, I have never used this before.
@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()