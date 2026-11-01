from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RAG Document Intelligence"
    api_prefix: str = "/api/v1"
    database_url: str = "sqlite:///./data/rag_intelligence.db"
    upload_dir: Path = Path("./uploads")
    chroma_dir: Path = Path("./chroma_data")
    max_upload_mb: int = 20
    chunk_size: int = 900
    chunk_overlap: int = 150
    embedding_provider: str = "sentence-transformers"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    generation_provider: str = "extractive"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2:3b"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def prepare(self) -> None:
        Path("data").mkdir(exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.prepare()
    return settings

