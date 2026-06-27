from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    # Providers
    GROQ_API_KEY: str = ""
    DEEPGRAM_API_KEY: str = ""
    CARTESIA_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    BEY_API_KEY: str = ""
    TAVUS_API_KEY: str = ""

    # Auth & System
    WORKER_API_SECRET: str = "dev-worker-secret"
    DATABASE_URL: str = "sqlite+aiosqlite:///./health_assistant.db"
    BACKEND_URL: str = "http://localhost:8000"
    
    # LiveKit
    LIVEKIT_URL: str = "ws://localhost:7880"
    LIVEKIT_API_KEY: str = "devkey"
    LIVEKIT_API_SECRET: str = "secret"
    LIVEKIT_HTTP_URL: str | None = None

    @property
    def livekit_http_url(self) -> str:
        if self.LIVEKIT_HTTP_URL:
            return self.LIVEKIT_HTTP_URL
        return self.LIVEKIT_URL.replace("ws://", "http://").replace("wss://", "https://")

settings = Settings()
