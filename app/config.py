"""Central settings, read from environment / .env (pydantic-settings)."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    llm_provider: str = "ollama"          # ollama | cloud
    mock_llm: bool = False
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_num_gpu: int | None = None     # 0 = CPU only (small GPUs crash on partial offload)
    cloud_base_url: str = ""
    cloud_api_key: str = ""
    cloud_model: str = ""
    llm_timeout_s: float = 120.0
    classify_mode: str = "llm"            # llm | keyword (keyword = deterministic classifier, no LLM call)

    embed_model: str = "bge"              # bge | minilm
    top_k: int = 8
    not_found_threshold: float = 0.45     # min cosine similarity of best chunk
    chunk_strategy: str = "clause"        # clause | fixed (eval comparison)

    db_path: str = "data/structured/university.db"
    chroma_path: str = "chroma_db"
    chroma_mode: str = "local"            # local (PersistentClient, default) | cloud (Chroma Cloud)
    chroma_api_key: str = ""
    chroma_tenant: str = ""
    chroma_database: str = ""
    docs_dir: str = "data/documents"
    register_csv: str = "data/source_register.csv"
    rules_seed_csv: str = "data/rules_seed.csv"
    ocr_cache_dir: str = "data/ocr_cache"
    ocr_lang: str = "eng"
    ocr_engine: str = "auto"             # auto | tesseract | rapidocr
    session_ttl_min: int = 30

    def path(self, p: str) -> Path:
        q = Path(p)
        return q if q.is_absolute() else ROOT / q

    @property
    def model_label(self) -> str:
        if self.mock_llm:
            return "mock"
        return self.ollama_model if self.llm_provider == "ollama" else self.cloud_model


@lru_cache
def get_settings() -> Settings:
    return Settings()


NOT_FOUND_MESSAGE = "I could not find this information in the authorised university sources."
