from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────────
    app_name: str = "retail-analytics-agent"
    app_env: str = Field(default="development", pattern="^(development|staging|production)$")
    app_debug: bool = False
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_workers: int = Field(default=4, ge=1, le=16)
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    # ── OpenAI ───────────────────────────────────────────────────
    openai_api_key: str
    openai_model: str = "gpt-4o"
    openai_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    openai_max_tokens: int = Field(default=4096, ge=1, le=16384)
    openai_embedding_model: str = "text-embedding-3-small"

    # ── GCP ──────────────────────────────────────────────────────
    gcp_project_id: str
    gcp_region: str = "us-central1"
    gcp_bigquery_dataset: str = "retail_analytics"
    gcp_service_account_key_path: Optional[str] = None
    gcp_cloud_run_service_name: str = "retail-agent"

    # ── BigQuery Table Names ─────────────────────────────────────
    bq_products_table: str = "products"
    bq_inventory_table: str = "inventory"
    bq_sales_table: str = "sales"
    bq_forecasts_table: str = "forecasts"
    bq_reports_table: str = "reports"
    bq_customer_insights_table: str = "customer_insights"

    # ── Agent ────────────────────────────────────────────────────
    agent_max_iterations: int = Field(default=15, ge=1, le=50)
    agent_verbose: bool = False
    agent_timeout_seconds: int = Field(default=120, ge=10, le=600)

    # ── Forecasting ──────────────────────────────────────────────
    forecast_horizon_days: int = Field(default=30, ge=1, le=365)
    forecast_confidence_interval: float = Field(default=0.95, ge=0.5, le=0.999)
    forecast_min_historical_days: int = Field(default=90, ge=30, le=730)

    # ── Reporting ────────────────────────────────────────────────
    report_schedule_cron: str = "0 8 * * *"
    report_output_format: str = Field(default="json", pattern="^(json|pdf|csv)$")

    # ── Redis ────────────────────────────────────────────────────
    redis_url: Optional[str] = None
    redis_ttl_seconds: int = Field(default=3600, ge=60, le=86400)

    # ── CORS ─────────────────────────────────────────────────────
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:8000","http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def full_table_name(self, table: str) -> str:
        return f"{self.gcp_project_id}.{self.gcp_bigquery_dataset}.{table}"


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()