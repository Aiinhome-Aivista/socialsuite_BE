from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "Social Suite"
    ENV: str = "development"
    SECRET_KEY: str = "change-me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    TOKEN_ENCRYPTION_KEY: str = "a-tjvhqi2i9EgHK-Jk0yGK_nbv05i15vQ1WlOVz2LXY="

    # MySQL
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = "Dutta@2002"
    DB_NAME: str = "socialsuite"

    # Mistral
    MISTRAL_MODE: str = "cloud"  # cloud | local
    MISTRAL_API_KEY: str = ""
    MISTRAL_CLOUD_MODEL: str = "mistral-large-latest"
    MISTRAL_LOCAL_BASE_URL: str = "http://127.0.0.1:11434/v1"
    MISTRAL_LOCAL_MODEL: str = "mistral"
    MISTRAL_LOCAL_URL: str = ""

    # Chroma
    CHROMA_PERSIST_DIR: str = "./chroma_data"

    # Social (loaded lazily by each connector)
    FACEBOOK_APP_ID: str = ""
    FACEBOOK_APP_SECRET: str = ""
    FACEBOOK_REDIRECT_URI: str = ""
    INSTAGRAM_REDIRECT_URI: str = ""   # uses the same Meta app as Facebook
    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""
    LINKEDIN_REDIRECT_URI: str = ""
    X_CLIENT_ID: str = ""
    X_CLIENT_SECRET: str = ""
    X_REDIRECT_URI: str = ""
    YOUTUBE_CLIENT_ID: str = ""
    YOUTUBE_CLIENT_SECRET: str = ""
    YOUTUBE_REDIRECT_URI: str = ""
    GOOGLE_ANALYTICS_CLIENT_ID: str = ""
    GOOGLE_ANALYTICS_CLIENT_SECRET: str = ""
    GOOGLE_ANALYTICS_REDIRECT_URI: str = ""
    PINTEREST_APP_ID: str = ""
    PINTEREST_APP_SECRET: str = ""
    PINTEREST_REDIRECT_URI: str = ""
    PINTEREST_ENV: str = "sandbox"  # 'sandbox' or 'production'

    @property
    def database_url(self) -> str:
        import urllib.parse
        user = urllib.parse.quote_plus(self.DB_USER)
        password = urllib.parse.quote_plus(self.DB_PASSWORD)
        return (
            f"mysql+pymysql://{user}:{password}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
