from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/backend",
        validation_alias="DATABASE_URL",
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    sync_models: bool = Field(default=False, validation_alias="SYNC_MODELS")
    
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    tavily_api_key: str | None = Field(default=None, validation_alias="TAVILY_API_KEY")
    reddit_user_script: str | None = Field(default=None, validation_alias="REDDIT_USER_SCRIPT")
    reddit_secret: str | None = Field(default=None, validation_alias="REDDIT_SECRET")

    class Config:
        env_file = ".env"


settings = Settings()