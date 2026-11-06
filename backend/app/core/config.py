from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

class Settings(BaseSettings):
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    database_url: str = "postgresql+psycopg://intentos:intentos@localhost:5432/intentos"
    payment_mode: str = "mock"
    auth_tokens: dict[str,str] = {}
    auth_admins: list[str] = []

    @field_validator('auth_tokens')
    @classmethod
    def operator_credentials(cls,value):
        if any(len(token)<32 or not owner or len(owner)>160 for token,owner in value.items()):
            raise ValueError('Operator bearer credentials require at least 32 characters and a nonempty identity of at most 160 characters')
        return value
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

settings = Settings()
