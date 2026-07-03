"""Central configuration — all env vars, model IDs, and limits live here."""

from pydantic_settings import BaseSettings
from pydantic import SecretStr


class Settings(BaseSettings):
    # --- OpenCode Go ---
    opencode_api_key: SecretStr
    opencode_base_url: str = "https://opencode.ai/zen/go/v1"

    # --- Exa ---
    exa_api_key: SecretStr = SecretStr("dummy-key-for-tests")


    # --- Docker sandbox ---
    docker_timeout_s: int = 10
    sandbox_mem_limit_mb: int = 256
    sandbox_cpu_quota: float = 0.5  # fraction of 1 CPU core

    # --- Model assignments ---
    # Defaults below are used when no *_MODEL env var is set.
    # Override any agent's model without touching the others via:
    #   HOST_MODEL=gpt-4o  SABOTEUR_MODEL=claude-3.5-sonnet  EVALUATOR_MODEL=gpt-4o
    models: dict[str, str] = {
        "host": "glm-5.2",
        "saboteur": "deepseek-v4-pro",
        "evaluator": "kimi-k2.7-code",
    }
    host_model: str | None = None
    saboteur_model: str | None = None
    evaluator_model: str | None = None

    # --- Agent params ---
    host_temperature: float = 0.4
    host_max_tokens: int = 1500
    saboteur_temperature: float = 0.7
    saboteur_max_tokens: int = 2500
    evaluator_temperature: float = 1.0
    evaluator_max_tokens: int = 1500

    # --- Demo ---
    max_rounds: int = 1
    max_bugs_per_difficulty: dict[str, int] = {
        "easy": 1,
        "medium": 2,
        "hard": 3,
    }
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]  # Add deployed URL via ALLOWED_ORIGINS env
    sandbox_python_image: str = "agentx-sandbox-python:latest"
    sandbox_node_image: str = "agentx-sandbox-node:latest"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Apply per-agent env overrides on top of the default dict — only
        # the agents whose *_MODEL env var is set are changed; the rest keep
        # their hardcoded defaults.
        for key, override in (
            ("host", self.host_model),
            ("saboteur", self.saboteur_model),
            ("evaluator", self.evaluator_model),
        ):
            if override:
                self.models[key] = override


settings = Settings()
