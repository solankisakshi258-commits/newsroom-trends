"""Configuration loading: config.yaml for behavior, .env for secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv optional; env vars still work without it
    def load_dotenv(*_a: Any, **_k: Any) -> bool:  # type: ignore
        return False


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


@dataclass(slots=True)
class Config:
    """Parsed configuration. `raw` keeps the full dict for connector-specific reads."""

    raw: dict[str, Any]
    project_root: Path
    secrets: dict[str, str] = field(default_factory=dict)

    # ---- convenience accessors -------------------------------------------------
    def source(self, name: str) -> dict[str, Any]:
        return self.raw.get("sources", {}).get(name, {}) or {}

    def source_enabled(self, name: str) -> bool:
        return bool(self.source(name).get("enabled", False))

    @property
    def competitors(self) -> list[dict[str, str]]:
        return self.raw.get("competitors", []) or []

    @property
    def clustering(self) -> dict[str, Any]:
        return self.raw.get("clustering", {}) or {}

    @property
    def scoring(self) -> dict[str, Any]:
        return self.raw.get("scoring", {}) or {}

    @property
    def schedule(self) -> dict[str, Any]:
        return self.raw.get("schedule", {}) or {}

    @property
    def dashboard(self) -> dict[str, Any]:
        return self.raw.get("dashboard", {}) or {}

    @property
    def alerts(self) -> dict[str, Any]:
        return self.raw.get("alerts", {}) or {}

    @property
    def db_path(self) -> Path:
        p = self.raw.get("storage", {}).get("db_path", "data/trends.db")
        return self._resolve(p)

    @property
    def reports_dir(self) -> Path:
        p = self.raw.get("storage", {}).get("reports_dir", "data/reports")
        return self._resolve(p)

    def secret(self, key: str) -> str | None:
        val = self.secrets.get(key) or os.environ.get(key)
        return val or None

    def _resolve(self, p: str) -> Path:
        path = Path(p)
        return path if path.is_absolute() else self.project_root / path


def load_config(path: str | Path | None = None) -> Config:
    """Load config.yaml and .env. Missing .env is fine."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(f"config not found: {cfg_path}")

    root = cfg_path.resolve().parent
    load_dotenv(root / ".env")

    with cfg_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    # Collect the secrets we know about so connectors don't each reach into os.environ.
    secret_keys = [
        "YOUTUBE_API_KEY",
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_USER_AGENT",
        "TWITTER_BEARER_TOKEN",
        "ALERT_WEBHOOK_URL",
    ]
    secrets = {k: os.environ[k] for k in secret_keys if os.environ.get(k)}

    return Config(raw=raw, project_root=root, secrets=secrets)
