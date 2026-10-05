from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Find the project root directory
BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()


# if __name__ == "__main__":
#     print("Database:", settings.DATABASE_URL)
#     print("Secret configured:", bool(settings.SECRET_KEY))
#     print("Token expiry:", settings.ACCESS_TOKEN_EXPIRE_MINUTES)
