from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "trainium"

    gemini_api_key: str = ""
    gemini_model_live: str = "gemini-3.5-transcribe-live"
    gemini_model_flash: str = "gemini-3.8-flash"
    gemini_model_flash_lite: str = "gemini-3.5-flash-lite"
    gemini_model_tts: str = "gemini-3.1-flash-tts-preview"
    # Analysis runs after the session, so it is not on the latency path and
    # can afford the stronger model. Scoring against rubric anchors needs
    # better reasoning than the Director's quick in-character lines.
    gemini_model_analysis: str = "gemini-3.8-flash"
    # Share of the deck a trainer is expected to get through for the session to
    # count as covering its material. Below this, Time Management is marked
    # down however well the session otherwise ran. Configurable because what
    # counts as complete differs by course: a concept session may legitimately
    # dwell on a third of the slides, a product walkthrough may not.
    trainium_coverage_threshold: float = 0.6
    # Sessions the golden set needs before an agreement result means anything.
    # From the architecture doc's calibration plan; a gate cleared on three
    # sessions is not a gate.
    trainium_golden_set_size: int = 20

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""

    cors_origins: str = "http://localhost:3000"
    soffice_path: str = "soffice"

    class Config:
        env_file = ".env"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
