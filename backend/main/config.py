from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "trainium"

    gemini_api_key: str = ""
    gemini_model_live: str = "gemini-3.8-live"
    gemini_model_flash: str = "gemini-3.8-flash"
    gemini_model_tts: str = "gemini-3.1-flash-tts-preview"

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""

    cors_origins: str = "http://localhost:3000"

    class Config:
        env_file = ".env"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
