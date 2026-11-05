from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    database_url: str = "postgresql+psycopg://intentos:intentos@localhost:5432/intentos"
    payment_mode: str = "mock"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
