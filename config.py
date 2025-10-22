from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./test.db"
    secret_key: str = "your-secret-key-here"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    tavily_api_key: str | None = Field(default=None, validation_alias="TAVILY_API_KEY")

    class Config:
        env_file = ".env"

settings = Settings()