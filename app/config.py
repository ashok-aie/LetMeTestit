"""
Application Configuration Module
Loads and validates settings from environment variables and .env file.
"""
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # 1. Jira Cloud Configuration
    jira_base_url: str = Field(default="https://your-company.atlassian.net", alias="JIRA_BASE_URL")
    jira_user_email: str = Field(default="qa-engineer@example.com", alias="JIRA_USER_EMAIL")
    jira_api_token: str = Field(default="", alias="JIRA_API_TOKEN")

    # 2. Local LLM Runtime (Ollama)
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="qwen2.5:7b", alias="OLLAMA_MODEL")
    ollama_timeout_seconds: int = Field(default=300, alias="OLLAMA_TIMEOUT_SECONDS")

    # 3. Environment & Security Guardrails
    app_env: str = Field(default="local", alias="APP_ENV")
    allowed_domains_raw: str = Field(default="localhost,127.0.0.1,s4srv25.nodomain.com,nodomain.com,183.82.97.234", alias="ALLOWED_DOMAINS")
    demo_app_url: str = Field(default="http://localhost:8000", alias="DEMO_APP_URL")

    # SAP S/4HANA Environment Settings
    sap_fiori_url: str = Field(
        default="https://s4srv25.nodomain.com:44325/sap/bc/ui2/flp?sap-client=100&sap-language=EN#Launchpad-openFLPPage?pageId=SAP_CRM_PG_SERVICE_PROCESSING&spaceId=SAP_CRM_SP_SERVICE",
        alias="SAP_FIORI_URL",
    )
    sap_username: str = Field(default="", alias="SAP_USERNAME")
    sap_password: str = Field(default="", alias="SAP_PASSWORD")
    sap_client: str = Field(default="100", alias="SAP_CLIENT")
    sap_language: str = Field(default="EN", alias="SAP_LANGUAGE")
    sap_host_ip: str = Field(default="183.82.97.234", alias="SAP_HOST_IP")
    sap_host_domain: str = Field(default="s4srv25.nodomain.com", alias="SAP_HOST_DOMAIN")

    # 4. Playwright Browser Automation
    browser_headless: bool = Field(default=True, alias="BROWSER_HEADLESS")
    cdp_endpoint_url: str = Field(default="", alias="CDP_ENDPOINT_URL")
    browser_step_timeout_ms: int = Field(default=10000, alias="BROWSER_STEP_TIMEOUT_MS")
    browser_slow_mo_ms: int = Field(default=0, alias="BROWSER_SLOW_MO_MS")

    # 5. Persistence & Evidence Storage
    sqlite_db_path: str = Field(default="testpilot.db", alias="SQLITE_DB_PATH")
    artifacts_dir: str = Field(default="artifacts", alias="ARTIFACTS_DIR")

    # 6. Cloud LLM API Keys
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    antigravity_api_key: str = Field(default="", alias="ANTIGRAVITY_API_KEY")

    # 7. Langfuse Observability & Telemetry
    langfuse_enabled: bool = Field(default=True, alias="LANGFUSE_ENABLED")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", alias="LANGFUSE_HOST")

    @property
    def allowed_domains(self) -> List[str]:
        """Returns allowed domains as a clean list of trimmed strings."""
        return [d.strip() for d in self.allowed_domains_raw.split(",") if d.strip()]

    @property
    def target_base_url(self) -> str:
        """Alias for demo_app_url used across test runner and designer."""
        return self.demo_app_url


# Global singleton settings instance
settings = Settings()

# Propagate Langfuse telemetry configuration to environment variables
import os

if settings.langfuse_enabled and settings.langfuse_public_key and settings.langfuse_secret_key:
    os.environ["LANGFUSE_PUBLIC_KEY"] = settings.langfuse_public_key
    os.environ["LANGFUSE_SECRET_KEY"] = settings.langfuse_secret_key
    os.environ["LANGFUSE_HOST"] = settings.langfuse_host

