from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+asyncpg://aiops:aiops@localhost:5432/aiops"
    internal_api_key: str = ""
    opensearch_url: str = "http://localhost:9200"
    opensearch_username: str = ""
    opensearch_password: str = ""
    opensearch_verify_certs: bool = True
    opensearch_ca_certs: str | None = None
    opensearch_logs_index: str = "aiops-logs-v1-*"
    enable_opensearch: bool = False
    enable_alert_ingestion: bool = False
    enable_canonical_reads: bool = False
    canonical_read_token: str = ""
    core_read_url: str = ""
    evidence_read_url: str = ""
    twin_read_url: str = ""
    max_query_hours: int = 24


settings = Settings()
