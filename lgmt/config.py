"""Configuration resolution: defaults < YAML file < env vars < CLI flags."""
import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import yaml

ENV_API_KEY = "LGMT_API_KEY"
ENV_BASE_URL = "LGMT_BASE_URL"
ENV_MODEL = "LGMT_MODEL"


@dataclass
class Settings:
    """Resolved LGMT settings."""

    model: str = "gpt-4o"
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    temperature: float = 0.0
    max_workers: int = 100
    prompting: str = "zero_cot"
    models_map: Dict[str, str] = field(default_factory=dict)


def load_config_file(config_path: Optional[str]) -> Dict[str, Any]:
    """Load the YAML config file; missing file yields empty config."""
    if not config_path:
        return {}
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_settings(
    config_path: Optional[str] = None,
    cli_overrides: Optional[Dict[str, Any]] = None,
) -> Settings:
    """Merge defaults, config file, environment variables, and CLI flags.

    Precedence (low to high): built-in defaults < YAML config file
    (``model.*`` / ``inference.*``) < ``LGMT_*`` environment variables <
    explicit CLI overrides.
    """
    file_cfg = load_config_file(config_path)
    model_cfg = file_cfg.get("model", {}) or {}
    infer_cfg = file_cfg.get("inference", {}) or {}

    settings = Settings(
        model=model_cfg.get("name", Settings.model),
        base_url=model_cfg.get("base_url"),
        api_key=model_cfg.get("api_key") or None,
        temperature=float(model_cfg.get("temperature", 0.0)),
        max_workers=int(infer_cfg.get("max_workers", 100)),
        prompting=infer_cfg.get("prompting", "zero_cot"),
        models_map=dict(model_cfg.get("aliases", {}) or {}),
    )

    if os.environ.get(ENV_MODEL):
        settings.model = os.environ[ENV_MODEL]
    if os.environ.get(ENV_BASE_URL):
        settings.base_url = os.environ[ENV_BASE_URL]
    if os.environ.get(ENV_API_KEY):
        settings.api_key = os.environ[ENV_API_KEY]

    for key, value in (cli_overrides or {}).items():
        if value is not None and hasattr(settings, key):
            setattr(settings, key, value)
    return settings
